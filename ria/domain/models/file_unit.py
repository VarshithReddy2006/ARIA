"""File unit entity.

Implements Twin Spec section 3.2, entity ``FileUnit``. The design decision the
specification attaches to this entity is section 6.4's content addressing:

    "The unit of index reuse is ``(content_hash, language, extractor_version)``.
    A file identical in two branches is parsed once; a file unchanged across
    commits is never reparsed."

A :class:`FileUnit` therefore carries two identities at once. ``path`` and the
derived :attr:`FileUnit.moniker` give logical identity within a commit;
``content_hash`` gives physical identity across every commit and branch in the
system. Both are mandatory, and neither substitutes for the other.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

from ria.domain.enums import (
    FileClassification,
    LanguageTier,
    ParseStatus,
)
from ria.domain.identity import CommitSha, ContentHash, Moniker, RepositoryId
from ria.domain.language import UNKNOWN_LANGUAGE
from ria.domain.paths import normalise_repository_path, parent_directory

__all__ = ["FileUnit"]


@dataclass(frozen=True)
class FileUnit:
    """One file as it exists at one commit.

    Attributes:
        repository_id: Owning repository.
        commit_sha: Commit this unit belongs to. Facts are commit-scoped
            (Twin Spec section 3.1, Rule 2).
        path: Repository-relative POSIX path. Normalised at construction.
        content_hash: Physical identity of the file's bytes.
        blob_sha: Git blob object name, retained so that content can be re-read
            from the git mirror without consulting the content store.
        language: Canonical language name, or ``"unknown"``.
        language_tier: Extraction tier available for the language, which bounds
            the resolution method any relation derived from this file can reach.
        size_bytes: File size.
        line_count: Number of lines. ``None`` when not counted, for example for
            binary files or files skipped by admission limits.
        classification: Role of the file in the repository.
        parse_status: Parse outcome. ``PENDING`` until the parser layer runs.
        parse_status_reason: Why parsing did not fully succeed. Mandatory for
            ``UNPARSEABLE`` and ``SKIPPED`` so that a coverage gap always states
            its cause (PRD principle P11).
        module_moniker: Owning module. ``None`` until the module graph exists in
            Milestone 5.
    """

    repository_id: RepositoryId
    commit_sha: CommitSha
    path: str
    content_hash: ContentHash
    blob_sha: str
    language: str = UNKNOWN_LANGUAGE
    language_tier: LanguageTier = LanguageTier.NONE
    size_bytes: int = 0
    line_count: Optional[int] = None
    classification: FileClassification = FileClassification.UNKNOWN
    parse_status: ParseStatus = ParseStatus.PENDING
    parse_status_reason: Optional[str] = None
    module_moniker: Optional[Moniker] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", normalise_repository_path(self.path))
        if not self.blob_sha:
            raise ValueError("blob_sha must be non-empty")
        if self.size_bytes < 0:
            raise ValueError(f"size_bytes must be non-negative, got {self.size_bytes}")
        if self.line_count is not None and self.line_count < 0:
            raise ValueError(f"line_count must be non-negative, got {self.line_count}")
        if not self.language:
            raise ValueError(
                "language must be non-empty; use the unknown sentinel instead"
            )
        if (
            self.parse_status in (ParseStatus.UNPARSEABLE, ParseStatus.SKIPPED)
            and not self.parse_status_reason
        ):
            raise ValueError(
                f"parse_status_reason is mandatory when parse_status is {self.parse_status}"
            )

    # -- identity ---------------------------------------------------------

    @property
    def moniker(self) -> Moniker:
        """Logical identity of this file, of the form ``file:.:path``."""
        return Moniker.for_file(self.path)

    @property
    def directory(self) -> str:
        """Parent directory path. Empty string for a file at the repository root."""
        return parent_directory(self.path)

    @property
    def reuse_key(self) -> str:
        """Cache key for parse reuse across commits and branches.

        Implements the reuse unit of Twin Spec section 6.4. The extractor version
        is deliberately not part of this key: it is appended by the parser layer
        in Milestone 3, which owns that version. Combining them here would couple
        the ingestion layer to a parser concern.

        Returns:
            A string identifying the content and language of this unit.
        """
        return f"{self.content_hash}|{self.language}"

    # -- predicates -------------------------------------------------------

    @property
    def is_parse_candidate(self) -> bool:
        """Whether the parser layer should attempt extraction on this unit.

        A unit is a candidate when its classification permits parsing and a
        language was detected. Note that a candidate may still have
        ``language_tier`` of ``NONE``, meaning it is recognised but no extractor
        is installed; that distinction is what
        :meth:`~ria.domain.models.commit.CommitCoverage` reports honestly.
        """
        return (
            self.classification.is_parseable_candidate
            and self.language != UNKNOWN_LANGUAGE
        )

    @property
    def counts_toward_metrics(self) -> bool:
        """Whether this unit participates in health, churn and hotspot metrics."""
        return self.classification.counts_toward_metrics

    # -- transformations --------------------------------------------------

    def with_parse_outcome(
        self,
        status: ParseStatus,
        *,
        reason: Optional[str] = None,
    ) -> "FileUnit":
        """Return a copy recording a parse outcome.

        Args:
            status: Parse outcome to record.
            reason: Explanation, mandatory for ``UNPARSEABLE`` and ``SKIPPED``.

        Returns:
            A new :class:`FileUnit` with the outcome recorded.

        Raises:
            ValueError: If a reason is required for the status but absent.
        """
        return replace(self, parse_status=status, parse_status_reason=reason)

    def with_module(self, module_moniker: Moniker) -> "FileUnit":
        """Return a copy attached to a module.

        Args:
            module_moniker: Moniker of the owning module.
        """
        return replace(self, module_moniker=module_moniker)

    def __str__(self) -> str:
        return f"{self.path}@{self.commit_sha.short}"
