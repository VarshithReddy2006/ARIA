"""Commit manifest.

Implements the ``CommitManifest`` output of SDD section 3 (L1):

    ``CommitManifest { repo_id, commit_sha, parent_shas, tree: [FileUnit{...}] }``

The manifest is the boundary artefact between ingestion and everything above it.
It is a complete, immutable description of one commit's tree, and it is what
change detection in Milestone 2 diffs against.

Design note
-----------
The manifest owns lookup indexes over its tree (:meth:`CommitManifest.by_path`,
:meth:`CommitManifest.content_hashes`) rather than leaving callers to rebuild
them. Milestone 2's diff engine performs three separate lookups per file over
trees of up to 500,000 entries; building those indexes once, here, is the
difference between a linear and a quadratic diff.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, FrozenSet, Mapping, Optional, Tuple

from ria.domain.enums import FileClassification
from ria.domain.identity import CommitSha, ContentHash, RepositoryId
from ria.domain.models.file_unit import FileUnit

__all__ = ["CommitManifest"]


@dataclass(frozen=True)
class CommitManifest:
    """The complete file tree of one commit.

    Attributes:
        repository_id: Owning repository.
        commit_sha: Commit the tree describes.
        parent_shas: Parent commits, in git order.
        tree: Every file unit in the commit, in ascending path order.
        created_at: When the manifest was produced.
        truncated: Whether the tree omits entries because an admission limit was
            reached. A truncated manifest must never be presented as complete;
            SDD section 3 (L1) requires rejection over silent partial ingestion,
            so this flag exists to make an accidental partial manifest
            detectable rather than to license one.
    """

    repository_id: RepositoryId
    commit_sha: CommitSha
    parent_shas: Tuple[CommitSha, ...]
    tree: Tuple[FileUnit, ...]
    created_at: datetime
    truncated: bool = False

    #: Lazily built path index. Excluded from equality and construction.
    _path_index: Dict[str, FileUnit] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        ordered = tuple(sorted(self.tree, key=lambda unit: unit.path))
        object.__setattr__(self, "tree", ordered)
        object.__setattr__(self, "parent_shas", tuple(self.parent_shas))

        index: Dict[str, FileUnit] = {}
        for unit in ordered:
            if unit.commit_sha != self.commit_sha:
                raise ValueError(
                    f"file unit {unit.path!r} belongs to commit {unit.commit_sha} "
                    f"but manifest describes {self.commit_sha}"
                )
            if unit.repository_id != self.repository_id:
                raise ValueError(
                    f"file unit {unit.path!r} belongs to a different repository"
                )
            if unit.path in index:
                raise ValueError(f"duplicate path in manifest tree: {unit.path!r}")
            index[unit.path] = unit
        object.__setattr__(self, "_path_index", index)

    # -- lookup -----------------------------------------------------------

    def by_path(self) -> Mapping[str, FileUnit]:
        """Index of the tree by normalised path.

        Returns:
            A read-only mapping from path to file unit.
        """
        return self._path_index

    def get(self, path: str) -> Optional[FileUnit]:
        """Look up a file unit by normalised path.

        Args:
            path: Normalised repository-relative path.

        Returns:
            The unit, or ``None`` if the path is absent from this commit.
        """
        return self._path_index.get(path)

    def paths(self) -> FrozenSet[str]:
        """Set of every path present in the commit."""
        return frozenset(self._path_index)

    def content_hashes(self) -> Mapping[str, ContentHash]:
        """Map every path to the content hash of its bytes.

        This is the input to change detection: comparing two of these mappings
        yields added, modified and deleted paths without reading any file.
        """
        return {path: unit.content_hash for path, unit in self._path_index.items()}

    def distinct_content_hashes(self) -> FrozenSet[ContentHash]:
        """Every distinct content hash in the tree.

        Distinct rather than per-path because identical files at different paths
        share one blob and must be stored and parsed once.
        """
        return frozenset(unit.content_hash for unit in self.tree)

    # -- aggregates -------------------------------------------------------

    @property
    def file_count(self) -> int:
        """Number of file units in the tree."""
        return len(self.tree)

    @property
    def total_bytes(self) -> int:
        """Aggregate size of every file in the tree."""
        return sum(unit.size_bytes for unit in self.tree)

    @property
    def is_merge(self) -> bool:
        """Whether the described commit has more than one parent."""
        return len(self.parent_shas) > 1

    def units_by_classification(
        self, classification: FileClassification
    ) -> Tuple[FileUnit, ...]:
        """Every unit with a given classification.

        Args:
            classification: Classification to filter by.
        """
        return tuple(
            unit for unit in self.tree if unit.classification is classification
        )

    def parse_candidates(self) -> Tuple[FileUnit, ...]:
        """Every unit the parser layer should attempt to extract from."""
        return tuple(unit for unit in self.tree if unit.is_parse_candidate)

    def language_line_counts(self) -> Mapping[str, int]:
        """Lines of code per language across units that count toward metrics.

        Units with no counted lines contribute nothing. Vendored and generated
        code is excluded, per :class:`~ria.domain.enums.FileClassification`.

        Returns:
            Mapping from canonical language name to line count.
        """
        totals: Dict[str, int] = {}
        for unit in self.tree:
            if not unit.counts_toward_metrics or unit.line_count is None:
                continue
            totals[unit.language] = totals.get(unit.language, 0) + unit.line_count
        return totals

    def __str__(self) -> str:
        return f"manifest({self.commit_sha.short}, {self.file_count} files)"
