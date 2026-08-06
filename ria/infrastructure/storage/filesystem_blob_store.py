"""Filesystem content-addressable store.

Implements :class:`~ria.ports.blob_store.ContentAddressableStore` over a sharded
directory tree.

Layout
------
``<root>/<shard>/<shard>/<digest>`` with shard depth and width from configuration.
Sharding bounds directory fan-out: a large monorepo contributes hundreds of
thousands of distinct blobs, and most filesystems degrade badly with that many
entries in one directory.

Durability
----------
Writes are atomic. Content is written to a temporary file in the same directory as
its final location, flushed, and then moved into place with :func:`os.replace`,
which is atomic on every supported platform when source and destination share a
filesystem. A reader therefore never observes a partially written blob, and a
crash mid-write leaves a temporary file that a later sweep can remove rather than
a corrupt blob that would falsify every fact derived from it.

Concurrency
-----------
Safe for concurrent writers, including across processes, because two workers
writing identical content write identical bytes and the final rename is atomic.
The last writer wins and the outcome is indistinguishable from the first writer
winning. This is the property that lets the ingestion worker pool of SDD section
6.3 write to one store without coordination.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Iterable, List, Optional, Tuple

from ria.domain.errors import BlobNotFoundError, StorageError
from ria.domain.identity import ContentHash
from ria.observability.logging import get_logger
from ria.ports.blob_store import BlobStat
from ria.ports.metrics import MetricsSink

__all__ = ["FilesystemBlobStore"]

_LOGGER = get_logger(__name__)

#: Metric names emitted by this adapter.
_METRIC_PUT_TOTAL = "ria_blob_put_total"
_METRIC_PUT_BYTES = "ria_blob_put_bytes_total"
_METRIC_GET_TOTAL = "ria_blob_get_total"
_METRIC_DELETE_TOTAL = "ria_blob_delete_total"

#: Read granularity for streaming writes.
_STREAM_CHUNK_BYTES = 1024 * 1024

#: Prefix of in-flight temporary files, so a sweep can identify them.
_TEMPORARY_PREFIX = ".incoming-"


class FilesystemBlobStore:
    """Content-addressable store backed by a sharded directory tree.

    Satisfies :class:`~ria.ports.blob_store.ContentAddressableStore`.

    Args:
        root: Directory beneath which blobs are stored. Created if absent.
        metrics: Sink for operation counts and byte volumes.
        shard_depth: Number of nested shard directories.
        shard_width: Characters consumed per shard directory.

    Raises:
        StorageError: If the root directory cannot be created.
    """

    def __init__(
        self,
        root: Path,
        metrics: MetricsSink,
        *,
        shard_depth: int = 2,
        shard_width: int = 2,
    ) -> None:
        self._root = Path(root)
        self._metrics = metrics
        self._shard_depth = shard_depth
        self._shard_width = shard_width
        try:
            self._root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageError(
                "blob store root could not be created",
                {"root": str(self._root), "reason": str(exc)},
            ) from exc

    # -- ContentAddressableStore ------------------------------------------

    def put(self, data: bytes) -> ContentHash:
        """Store content and return its identity.

        Args:
            data: Content to store.

        Returns:
            The content hash under which the content is stored.

        Raises:
            StorageError: If the content could not be written durably.
        """
        content_hash = ContentHash.of_bytes(data)
        target = self._path_for(content_hash)
        if target.exists():
            self._metrics.increment(
                _METRIC_PUT_TOTAL, labels={"outcome": "deduplicated"}
            )
            return content_hash
        self._write_atomically(target, (data,))
        self._metrics.increment(_METRIC_PUT_TOTAL, labels={"outcome": "written"})
        self._metrics.increment(_METRIC_PUT_BYTES, value=len(data))
        return content_hash

    def put_stream(self, stream: IO[bytes]) -> ContentHash:
        """Store content read from a stream without buffering it whole.

        The stream is read once into a temporary file while the digest is computed
        incrementally, then the temporary file is moved to its final location. This
        requires no seekable stream and never holds the whole content in memory.

        Args:
            stream: Readable binary stream positioned at the start of the content.

        Returns:
            The content hash under which the content is stored.

        Raises:
            StorageError: If the content could not be written durably.
        """
        digest = hashlib.sha256()
        written = 0
        temporary_path: Optional[Path] = None
        try:
            handle, temporary_name = tempfile.mkstemp(
                prefix=_TEMPORARY_PREFIX, dir=str(self._root)
            )
            temporary_path = Path(temporary_name)
            with os.fdopen(handle, "wb") as sink:
                while True:
                    chunk = stream.read(_STREAM_CHUNK_BYTES)
                    if not chunk:
                        break
                    digest.update(chunk)
                    sink.write(chunk)
                    written += len(chunk)
                sink.flush()
                os.fsync(sink.fileno())

            content_hash = ContentHash(f"{ContentHash.ALGORITHM}:{digest.hexdigest()}")
            target = self._path_for(content_hash)
            if target.exists():
                self._metrics.increment(
                    _METRIC_PUT_TOTAL, labels={"outcome": "deduplicated"}
                )
                return content_hash
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(str(temporary_path), str(target))
            temporary_path = None
            self._metrics.increment(_METRIC_PUT_TOTAL, labels={"outcome": "written"})
            self._metrics.increment(_METRIC_PUT_BYTES, value=written)
            return content_hash
        except OSError as exc:
            raise StorageError(
                "blob could not be written from stream",
                {"root": str(self._root), "reason": str(exc)},
            ) from exc
        finally:
            if temporary_path is not None:
                self._discard(temporary_path)

    def get(self, content_hash: ContentHash) -> bytes:
        """Read stored content in full.

        Args:
            content_hash: Identity of the content.

        Returns:
            The stored bytes.

        Raises:
            BlobNotFoundError: If no content is stored under the hash.
            StorageError: If the content exists but could not be read.
        """
        target = self._path_for(content_hash)
        try:
            data = target.read_bytes()
        except FileNotFoundError as exc:
            raise BlobNotFoundError(
                "blob is absent from the store", {"content_hash": str(content_hash)}
            ) from exc
        except OSError as exc:
            raise StorageError(
                "blob could not be read",
                {"content_hash": str(content_hash), "reason": str(exc)},
            ) from exc
        self._metrics.increment(_METRIC_GET_TOTAL)
        return data

    def open(self, content_hash: ContentHash) -> IO[bytes]:
        """Open stored content as a readable binary stream.

        The caller owns the returned stream and must close it.

        Args:
            content_hash: Identity of the content.

        Returns:
            A readable binary stream.

        Raises:
            BlobNotFoundError: If no content is stored under the hash.
            StorageError: If the content exists but could not be opened.
        """
        target = self._path_for(content_hash)
        try:
            stream = target.open("rb")
        except FileNotFoundError as exc:
            raise BlobNotFoundError(
                "blob is absent from the store", {"content_hash": str(content_hash)}
            ) from exc
        except OSError as exc:
            raise StorageError(
                "blob could not be opened",
                {"content_hash": str(content_hash), "reason": str(exc)},
            ) from exc
        self._metrics.increment(_METRIC_GET_TOTAL)
        return stream

    def exists(self, content_hash: ContentHash) -> bool:
        """Whether content is stored under a hash.

        Args:
            content_hash: Identity to test.
        """
        return self._path_for(content_hash).exists()

    def stat(self, content_hash: ContentHash) -> Optional[BlobStat]:
        """Return metadata about stored content.

        Args:
            content_hash: Identity of the content.

        Returns:
            The metadata, or ``None`` if the content is absent.
        """
        target = self._path_for(content_hash)
        try:
            info = target.stat()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise StorageError(
                "blob metadata could not be read",
                {"content_hash": str(content_hash), "reason": str(exc)},
            ) from exc
        return BlobStat(
            content_hash=content_hash,
            size_bytes=info.st_size,
            stored_at=datetime.fromtimestamp(info.st_mtime, tz=timezone.utc),
        )

    def missing(self, hashes: Iterable[ContentHash]) -> Iterable[ContentHash]:
        """Filter a set of hashes down to those not yet stored.

        Duplicates in the input are collapsed, because a tree frequently contains
        the same content at several paths and testing it repeatedly is wasted work.

        Args:
            hashes: Candidate identities.

        Returns:
            Absent identities, in first-seen input order.
        """
        seen = set()
        absent: List[ContentHash] = []
        for content_hash in hashes:
            if content_hash.value in seen:
                continue
            seen.add(content_hash.value)
            if not self.exists(content_hash):
                absent.append(content_hash)
        return tuple(absent)

    def delete(self, content_hash: ContentHash) -> bool:
        """Remove stored content.

        Args:
            content_hash: Identity of the content to remove.

        Returns:
            ``True`` if content was removed, ``False`` if it was already absent.

        Raises:
            StorageError: If the content exists but could not be removed.
        """
        target = self._path_for(content_hash)
        try:
            target.unlink()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise StorageError(
                "blob could not be deleted",
                {"content_hash": str(content_hash), "reason": str(exc)},
            ) from exc
        self._metrics.increment(_METRIC_DELETE_TOTAL)
        return True

    # -- maintenance ------------------------------------------------------

    def sweep_incomplete_writes(self) -> int:
        """Remove temporary files left behind by interrupted writes.

        Safe to call at any time: a temporary file is never referenced by a fact,
        because a blob only becomes referenceable after its atomic rename.

        Returns:
            Number of temporary files removed.
        """
        removed = 0
        for candidate in self._root.glob(f"{_TEMPORARY_PREFIX}*"):
            if candidate.is_file() and self._discard(candidate):
                removed += 1
        if removed:
            _LOGGER.info(
                "removed interrupted blob writes",
                extra={"removed": removed, "root": str(self._root)},
            )
        return removed

    # -- internals --------------------------------------------------------

    def _path_for(self, content_hash: ContentHash | str) -> Path:
        """Resolve the absolute path of a blob.

        Args:
            content_hash: Identity of the content.
        """
        if isinstance(content_hash, str):
            content_hash = ContentHash(content_hash)
        relative = content_hash.shard_path(
            depth=self._shard_depth, width=self._shard_width
        )
        return self._root.joinpath(*relative.split("/"))

    def _write_atomically(self, target: Path, chunks: Tuple[bytes, ...]) -> None:
        """Write chunks to a temporary file and move it into place atomically.

        Args:
            target: Final location of the blob.
            chunks: Content to write, in order.

        Raises:
            StorageError: If the content could not be written durably.
        """
        temporary_path: Optional[Path] = None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            handle, temporary_name = tempfile.mkstemp(
                prefix=_TEMPORARY_PREFIX, dir=str(target.parent)
            )
            temporary_path = Path(temporary_name)
            with os.fdopen(handle, "wb") as sink:
                for chunk in chunks:
                    sink.write(chunk)
                sink.flush()
                os.fsync(sink.fileno())
            os.replace(str(temporary_path), str(target))
            temporary_path = None
        except OSError as exc:
            raise StorageError(
                "blob could not be written",
                {"target": str(target), "reason": str(exc)},
            ) from exc
        finally:
            if temporary_path is not None:
                self._discard(temporary_path)

    @staticmethod
    def _discard(path: Path) -> bool:
        """Delete a file, reporting failure rather than raising.

        Used only on cleanup paths, where raising would mask the original error.

        Args:
            path: File to delete.

        Returns:
            ``True`` if the file was removed.
        """
        try:
            path.unlink()
            return True
        except OSError as exc:
            _LOGGER.warning(
                "temporary blob file could not be removed",
                extra={"path": str(path), "reason": str(exc)},
            )
            return False
