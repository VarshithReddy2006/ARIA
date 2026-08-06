"""File enumeration, classification, content addressing and storage.

Turns a commit into a :class:`~ria.domain.models.manifest.CommitManifest`: every blob
in its tree, normalised, classified, content-addressed, and — where the content will
be read again — stored.

Pipeline per file
-----------------
::

    tree entry
      -> normalise path
      -> detect language, tier, classification
      -> decide handling  (skip · stream-hash · read-hash-store)
      -> content hash
      -> FileUnit

Handling decisions, and why
---------------------------
**Symlinks are skipped.** A symlink's blob content is its target path, which is not
source code. Following it would either escape the repository or duplicate a file
already enumerated at its real path.

**Blobs above ``max_blob_bytes`` are stream-hashed, never buffered.** The limit is
about memory, exactly as its setting documents. The unit is still recorded with a
real content hash computed in fixed-size chunks, marked
:attr:`~ria.domain.enums.ParseStatus.SKIPPED` with the reason stated. The
alternatives were both unacceptable: buffering defeats the limit, and omitting the
file would silently understate the tree, so the manifest would describe a commit that
never existed.

**Content is stored only for parse candidates.** The content store exists to feed
parsing and retrieval. Git remains the system of record for content (SDD section
6.2), so anything not stored is still recoverable from the mirror. Writing every
binary asset of every commit into the store would inflate it with content nothing
will ever read.

**Already-stored content is not re-read.** A single bulk presence query
(:meth:`~ria.ports.blob_store.ContentAddressableStore.missing`) precedes any read, so
a file unchanged since a previous commit costs one hash comparison rather than a read
and a write. This is where the incremental economics of Twin Spec section 6.4 are
actually realised.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from ria.domain.enums import (
    FileClassification,
    IngestionStage,
    LanguageTier,
    ParseStatus,
)
from ria.domain.errors import AdmissionRejectedError, InvalidPathError
from ria.domain.identity import CommitSha, ContentHash, RepositoryId
from ria.domain.language import UNKNOWN_LANGUAGE, LanguageCatalogue
from ria.domain.models.file_unit import FileUnit
from ria.domain.models.manifest import CommitManifest
from ria.domain.models.progress import ProgressEvent
from ria.domain.models.repository import AdmissionLimits
from ria.domain.paths import normalise_repository_path
from ria.observability.logging import get_logger
from ria.ports.blob_store import ContentAddressableStore
from ria.ports.clock import Clock
from ria.ports.git_client import GitClient, RawTreeEntry
from ria.ports.metrics import MetricsSink
from ria.ports.progress import ProgressSink

__all__ = ["EnumerationResult", "FileEnumerator"]

_LOGGER = get_logger(__name__)

#: Metric names emitted by this service.
_METRIC_FILES = "ria_ingestion_files_total"
_METRIC_BYTES = "ria_ingestion_bytes_total"
_METRIC_STAGE_SECONDS = "ria_ingestion_stage_seconds"

#: How often a progress event is emitted while walking a tree. Every file would
#: produce more events than any consumer can use on a large repository; a fixed
#: interval keeps the volume bounded regardless of tree size.
_PROGRESS_INTERVAL = 250

#: Chunk size used when streaming an oversized blob, in bytes.
_STREAM_CHUNK_BYTES = 1024 * 1024

#: Reasons recorded on a skipped unit. Constants rather than inline strings, because
#: they are persisted and a consumer may group coverage gaps by cause.
REASON_SYMLINK = "symlink is not source content"
REASON_TOO_LARGE = "exceeds max_blob_bytes"
REASON_UNKNOWN_LANGUAGE = "no language detected"
REASON_NOT_PARSEABLE = "classification is not parseable"

#: How a file's content is handled. Also used as a metric label, so the values are
#: part of the observability contract and are not free to change.
#: Content is read and written to the store.
_HANDLING_STORE = "stored"
#: Content is read and hashed, but not written to the store.
_HANDLING_READ = "hashed"
#: Content is hashed by streaming, and never held in memory.
_HANDLING_STREAM = "streamed"


@dataclass(frozen=True)
class EnumerationResult:
    """Outcome of enumerating one commit's tree.

    Attributes:
        manifest: The complete tree.
        blobs_stored: Blobs written to the content store by this call.
        blobs_reused: Blobs already present, so not read or written. The measure of
            incremental effectiveness.
        blobs_streamed: Blobs hashed without being buffered, because they exceeded
            the memory limit.
        bytes_read: Total bytes read from git.
    """

    manifest: CommitManifest
    blobs_stored: int
    blobs_reused: int
    blobs_streamed: int
    bytes_read: int

    @property
    def reuse_ratio(self) -> float:
        """Fraction of distinct blobs that were already stored, in ``[0, 1]``.

        The headline incremental metric: a small change to a large repository should
        approach one, and a value near zero on a re-ingestion indicates the content
        addressing is not working.
        """
        considered = self.blobs_stored + self.blobs_reused
        if considered == 0:
            return 1.0
        return self.blobs_reused / considered


class FileEnumerator:
    """Builds a commit manifest from a git tree.

    Args:
        git: Read access to the repository mirror.
        blob_store: Destination for content that will be read again.
        language_catalogue: Language detection and classification table.
        clock: Source of timestamps.
        metrics: Sink for counts and durations.
        progress: Destination for progress events.
        max_blob_bytes: Largest blob read into memory in one call.
    """

    def __init__(
        self,
        git: GitClient,
        blob_store: ContentAddressableStore,
        language_catalogue: LanguageCatalogue,
        clock: Clock,
        metrics: MetricsSink,
        progress: ProgressSink,
        *,
        max_blob_bytes: int,
    ) -> None:
        if max_blob_bytes <= 0:
            raise ValueError("max_blob_bytes must be positive")
        self._git = git
        self._blob_store = blob_store
        self._languages = language_catalogue
        self._clock = clock
        self._metrics = metrics
        self._progress = progress
        self._max_blob_bytes = max_blob_bytes

    def enumerate_commit(
        self,
        *,
        repository_id: RepositoryId,
        mirror_path: Path,
        sha: CommitSha,
        limits: AdmissionLimits,
        job_id: Optional[str] = None,
    ) -> EnumerationResult:
        """Enumerate, hash and store one commit's tree.

        Args:
            repository_id: Owning repository.
            mirror_path: Path of the repository mirror.
            sha: Commit to enumerate.
            limits: Admission limits to enforce before any content is read.
            job_id: Job driving the work, recorded on progress events.

        Returns:
            The enumeration outcome, including the manifest.

        Raises:
            AdmissionRejectedError: If the tree exceeds a stated limit.
            RefNotFoundError: If the commit does not exist.
            GitCommandError: If a git invocation fails.
            StorageError: If content cannot be stored.
        """
        entries = self._list_tree(repository_id, mirror_path, sha, job_id)
        self._enforce_admission(entries, limits, sha)

        classified = self._classify(entries)
        plan = self._plan_storage(classified)

        units, statistics = self._materialise(
            repository_id=repository_id,
            mirror_path=mirror_path,
            sha=sha,
            classified=classified,
            hashes_to_store=plan,
            job_id=job_id,
        )

        manifest = CommitManifest(
            repository_id=repository_id,
            commit_sha=sha,
            parent_shas=(),
            tree=tuple(units),
            created_at=self._clock.now(),
        )
        return EnumerationResult(manifest=manifest, **statistics)

    # -- stages -----------------------------------------------------------

    def _list_tree(
        self,
        repository_id: RepositoryId,
        mirror_path: Path,
        sha: CommitSha,
        job_id: Optional[str],
    ) -> Sequence[RawTreeEntry]:
        """Read the commit's tree.

        Args:
            repository_id: Owning repository.
            mirror_path: Path of the mirror.
            sha: Commit to read.
            job_id: Job driving the work.

        Returns:
            Every blob in the tree.
        """
        self._emit(
            repository_id,
            IngestionStage.ENUMERATE,
            sha=sha,
            job_id=job_id,
            completed=0,
            total=None,
            message="reading tree",
        )
        with self._metrics.timer(
            _METRIC_STAGE_SECONDS, labels={"stage": IngestionStage.ENUMERATE.value}
        ):
            entries = self._git.list_tree(mirror_path, sha.value)
        self._emit(
            repository_id,
            IngestionStage.ENUMERATE,
            sha=sha,
            job_id=job_id,
            completed=len(entries),
            total=len(entries),
        )
        return entries

    def _enforce_admission(
        self,
        entries: Sequence[RawTreeEntry],
        limits: AdmissionLimits,
        sha: CommitSha,
    ) -> None:
        """Reject an oversized tree before any content is read.

        SDD section 3 (L1) requires rejection "with a stated limit — never partially
        ingested silently". Enforced here, after listing and before reading, because
        the tree listing is cheap and reveals the size without touching content.

        Args:
            entries: Tree entries.
            limits: Limits to enforce.
            sha: Commit being enumerated, for the error context.

        Raises:
            AdmissionRejectedError: If a limit is exceeded.
        """
        if len(entries) > limits.max_files:
            raise AdmissionRejectedError(
                "commit tree exceeds the configured file limit",
                {
                    "sha": sha.value,
                    "files": len(entries),
                    "max_files": limits.max_files,
                },
            )
        total_bytes = sum(entry.size_bytes for entry in entries)
        if total_bytes > limits.max_total_bytes:
            raise AdmissionRejectedError(
                "commit tree exceeds the configured total size limit",
                {
                    "sha": sha.value,
                    "total_bytes": total_bytes,
                    "max_total_bytes": limits.max_total_bytes,
                },
            )

    def _classify(
        self, entries: Sequence[RawTreeEntry]
    ) -> Sequence["_ClassifiedEntry"]:
        """Normalise and classify every entry.

        An entry whose path cannot be normalised is dropped with a warning rather
        than aborting the enumeration, per the L1 rule that one bad file must not fail
        a build. It is dropped rather than recorded because a path that fails
        normalisation has no valid identity to record it under.

        Args:
            entries: Tree entries.

        Returns:
            The classified entries, excluding any with an unusable path.
        """
        classified: List[_ClassifiedEntry] = []
        for entry in entries:
            try:
                path = normalise_repository_path(entry.path)
            except InvalidPathError as exc:
                _LOGGER.warning(
                    "skipping tree entry with an unusable path",
                    extra={"path": entry.path, "reason": str(exc)},
                )
                self._metrics.increment(
                    _METRIC_FILES, labels={"outcome": "unusable_path"}
                )
                continue

            language = self._languages.detect_language(path)
            classification = self._languages.classify(path)
            tier = self._languages.tier_for(language)
            handling, reason = self._decide_handling(
                entry=entry, language=language, classification=classification
            )
            classified.append(
                _ClassifiedEntry(
                    entry=entry,
                    path=path,
                    language=language,
                    tier=tier,
                    classification=classification,
                    handling=handling,
                    reason=reason,
                )
            )
        return tuple(classified)

    def _decide_handling(
        self,
        *,
        entry: RawTreeEntry,
        language: str,
        classification: FileClassification,
    ) -> Tuple[str, Optional[str]]:
        """Decide how one entry's content is handled.

        Ordering is deliberate. A symlink is rejected before its size is considered,
        because its size is irrelevant. Size is considered before parseability,
        because an oversized parse candidate must still be recorded as size-skipped
        rather than as a candidate we failed to store.

        Args:
            entry: Tree entry.
            language: Detected language.
            classification: File classification.

        Returns:
            The handling decision and, when the content will not be stored, the
            reason recorded on the unit.
        """
        if entry.is_symlink:
            return _HANDLING_STREAM, REASON_SYMLINK
        if entry.size_bytes > self._max_blob_bytes:
            return _HANDLING_STREAM, REASON_TOO_LARGE
        if language == UNKNOWN_LANGUAGE:
            return _HANDLING_READ, REASON_UNKNOWN_LANGUAGE
        if not classification.is_parseable_candidate:
            return _HANDLING_READ, REASON_NOT_PARSEABLE
        return _HANDLING_STORE, None

    def _plan_storage(
        self, classified: Sequence["_ClassifiedEntry"]
    ) -> Dict[str, bool]:
        """Determine which blob object names still need their content stored.

        Not answerable before hashing, because the content store is keyed by content
        hash and a blob object name is not one. The plan is therefore keyed by blob
        object name and resolved to a store decision per unique blob, so identical
        content appearing at several paths is read once.

        Args:
            classified: Classified entries.

        Returns:
            Mapping from blob object name to whether its content must be read.
        """
        plan: Dict[str, bool] = {}
        for item in classified:
            existing = plan.get(item.entry.blob_sha)
            wants_content = item.handling in (_HANDLING_READ, _HANDLING_STORE)
            plan[item.entry.blob_sha] = bool(existing) or wants_content
        return plan

    def _materialise(
        self,
        *,
        repository_id: RepositoryId,
        mirror_path: Path,
        sha: CommitSha,
        classified: Sequence["_ClassifiedEntry"],
        hashes_to_store: Dict[str, bool],
        job_id: Optional[str],
    ) -> Tuple[Sequence[FileUnit], Dict[str, int]]:
        """Hash and store content, producing the file units.

        Content is read once per distinct blob object name and reused across every
        path holding it, so a repository with the same licence file in twenty
        directories performs one read.

        Args:
            repository_id: Owning repository.
            mirror_path: Path of the mirror.
            sha: Commit being enumerated.
            classified: Classified entries.
            hashes_to_store: Whether each blob's content must be read.
            job_id: Job driving the work.

        Returns:
            The file units and the statistics for :class:`EnumerationResult`.
        """
        units: List[FileUnit] = []
        by_blob: Dict[str, Tuple[ContentHash, Optional[int]]] = {}
        stored = 0
        reused = 0
        streamed = 0
        bytes_read = 0
        total = len(classified)

        self._emit(
            repository_id,
            IngestionStage.HASH,
            sha=sha,
            job_id=job_id,
            completed=0,
            total=total,
        )

        with self._metrics.timer(
            _METRIC_STAGE_SECONDS, labels={"stage": IngestionStage.HASH.value}
        ):
            for index, item in enumerate(classified, start=1):
                cached = by_blob.get(item.entry.blob_sha)
                if cached is not None:
                    content_hash, line_count = cached
                elif hashes_to_store.get(item.entry.blob_sha, False):
                    content = self._git.read_blob(mirror_path, item.entry.blob_sha)
                    bytes_read += len(content)
                    content_hash = ContentHash.of_bytes(content)
                    line_count = self._git.count_lines(content)
                    if item.handling == _HANDLING_STORE:
                        if self._blob_store.exists(content_hash):
                            reused += 1
                        else:
                            self._blob_store.put(content)
                            stored += 1
                    by_blob[item.entry.blob_sha] = (content_hash, line_count)
                else:
                    content_hash = self._stream_hash(mirror_path, item.entry.blob_sha)
                    line_count = None
                    streamed += 1
                    by_blob[item.entry.blob_sha] = (content_hash, line_count)

                units.append(
                    self._to_unit(repository_id, sha, item, content_hash, line_count)
                )
                self._metrics.increment(
                    _METRIC_FILES, labels={"outcome": item.handling}
                )

                if index % _PROGRESS_INTERVAL == 0:
                    self._emit(
                        repository_id,
                        IngestionStage.HASH,
                        sha=sha,
                        job_id=job_id,
                        completed=index,
                        total=total,
                    )

        self._metrics.increment(_METRIC_BYTES, value=bytes_read)
        self._emit(
            repository_id,
            IngestionStage.STORE,
            sha=sha,
            job_id=job_id,
            completed=total,
            total=total,
            message=f"stored {stored}, reused {reused}, streamed {streamed}",
        )
        statistics = {
            "blobs_stored": stored,
            "blobs_reused": reused,
            "blobs_streamed": streamed,
            "bytes_read": bytes_read,
        }
        return tuple(units), statistics

    def _stream_hash(self, mirror_path: Path, blob_sha: str) -> ContentHash:
        """Content-address a blob without holding it in memory.

        Args:
            mirror_path: Path of the mirror.
            blob_sha: Blob object name.

        Returns:
            The content hash.
        """
        with self._git.open_blob(mirror_path, blob_sha) as stream:
            return ContentHash.of_stream(stream, chunk_size=_STREAM_CHUNK_BYTES)

    @staticmethod
    def _to_unit(
        repository_id: RepositoryId,
        sha: CommitSha,
        item: "_ClassifiedEntry",
        content_hash: ContentHash,
        line_count: Optional[int],
    ) -> FileUnit:
        """Build the file unit for one classified entry.

        Args:
            repository_id: Owning repository.
            sha: Commit the unit belongs to.
            item: Classified entry.
            content_hash: Identity of the content.
            line_count: Line count, or ``None`` when not counted.

        Returns:
            The file unit, with a parse status reflecting how its content was handled.
        """
        if item.reason is None:
            parse_status = ParseStatus.PENDING
            reason = None
        else:
            parse_status = ParseStatus.SKIPPED
            reason = item.reason
        return FileUnit(
            repository_id=repository_id,
            commit_sha=sha,
            path=item.path,
            content_hash=content_hash,
            blob_sha=item.entry.blob_sha,
            language=item.language,
            language_tier=item.tier,
            size_bytes=item.entry.size_bytes,
            line_count=line_count,
            classification=item.classification,
            parse_status=parse_status,
            parse_status_reason=reason,
        )

    def _emit(
        self,
        repository_id: RepositoryId,
        stage: IngestionStage,
        *,
        sha: CommitSha,
        job_id: Optional[str],
        completed: int,
        total: Optional[int],
        message: Optional[str] = None,
    ) -> None:
        """Emit one progress event.

        Args:
            repository_id: Owning repository.
            stage: Pipeline stage.
            sha: Commit being processed.
            job_id: Job driving the work.
            completed: Units of work finished.
            total: Units of work in the stage, or ``None`` if unknown.
            message: Optional detail.
        """
        self._progress.emit(
            ProgressEvent(
                repository_id=repository_id,
                stage=stage,
                at=self._clock.now(),
                job_id=job_id,
                commit_sha=sha.value,
                completed=completed,
                total=total,
                message=message,
            )
        )


@dataclass(frozen=True)
class _ClassifiedEntry:
    """One tree entry with its derived classification and handling decision.

    Internal to this module: it exists to carry the result of classification into
    materialisation without passing six parallel sequences.
    """

    entry: RawTreeEntry
    path: str
    language: str
    tier: LanguageTier
    classification: FileClassification
    handling: str
    reason: Optional[str]
