"""Change set between two commits.

Implements the ``ChangeSet`` output of SDD section 3 (L1)::

    diff(repo, base_sha, head_sha) -> ChangeSet { added, modified, deleted, renamed }

Produced by :func:`ria.domain.diff.compute_change_set`, which is a pure function over
two ``path -> content_hash`` mappings.

Why this is a value object rather than a service result
-------------------------------------------------------
Twin Spec section 6.1 makes the change set the input to step 3 of an incremental
build: ``affected = changed ∪ reverse_deps(changed)``. Every later milestone reads
it — the parser layer to decide what to reparse, the resolution layer to decide what
to rebind, the graph layer to decide which edges to invalidate. Making it an
immutable value with derived accessors means those consumers cannot disagree about
what "changed" means.

Categories are disjoint
-----------------------
A path appears in exactly one of ``added``, ``modified``, ``deleted``, or as one end
of a rename. The invariant is enforced at construction rather than documented,
because a consumer that processed overlapping categories would parse the same file
twice or invalidate a path it had just rebuilt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Mapping, Optional, Tuple

__all__ = ["RenamedPath", "ChangeSet"]


@dataclass(frozen=True)
class RenamedPath:
    """A file whose content moved unchanged from one path to another.

    Both endpoints share a content hash, which is what makes the rename exact rather
    than probabilistic. Twin Spec section 3.2 states that under content addressing
    "rename detection becomes a manifest concern only", and this type is that
    concern: the parse result keyed by the content hash remains valid, and only the
    path-to-symbol mapping moves.

    Attributes:
        previous_path: Path in the base commit.
        current_path: Path in the head commit.
        content_hash: Canonical content hash shared by both paths.
    """

    previous_path: str
    current_path: str
    content_hash: str

    def __post_init__(self) -> None:
        if not self.previous_path or not self.current_path:
            raise ValueError("a rename requires both paths")
        if self.previous_path == self.current_path:
            raise ValueError("a rename requires two distinct paths")
        if not self.content_hash:
            raise ValueError("a rename requires the shared content hash")

    def __str__(self) -> str:
        return f"{self.previous_path} -> {self.current_path}"


@dataclass(frozen=True)
class ChangeSet:
    """The complete difference between two commits' file trees.

    Attributes:
        head_sha: Commit compared to.
        base_sha: Commit compared from, or ``None`` when there is no base and every
            path is therefore an addition.
        added: Head paths absent from the base, excluding rename targets.
        modified: Paths present in both commits with differing content.
        deleted: Base paths absent from the head, excluding rename sources.
        renamed: Files whose content moved unchanged between paths.
    """

    head_sha: str
    base_sha: Optional[str] = None
    added: FrozenSet[str] = frozenset()
    modified: FrozenSet[str] = frozenset()
    deleted: FrozenSet[str] = frozenset()
    renamed: Tuple[RenamedPath, ...] = ()

    def __post_init__(self) -> None:
        if not self.head_sha:
            raise ValueError("head_sha must be non-empty")
        if self.base_sha is not None and self.base_sha == self.head_sha:
            raise ValueError("a change set requires two distinct commits")
        if self.base_sha is None and (self.modified or self.deleted or self.renamed):
            raise ValueError(
                "without a base commit every path is an addition; modified, deleted "
                "and renamed must be empty"
            )

        object.__setattr__(self, "added", frozenset(self.added))
        object.__setattr__(self, "modified", frozenset(self.modified))
        object.__setattr__(self, "deleted", frozenset(self.deleted))
        object.__setattr__(
            self,
            "renamed",
            tuple(sorted(self.renamed, key=lambda rename: rename.current_path)),
        )

        self._assert_disjoint()

    def _assert_disjoint(self) -> None:
        """Verify that no path appears in more than one category.

        Raises:
            ValueError: If any two categories overlap. Overlap would cause a
                consumer to reparse a file it had already handled, or to invalidate a
                path it had just rebuilt.
        """
        for first, second in (
            ("added", "modified"),
            ("added", "deleted"),
            ("modified", "deleted"),
        ):
            overlap = getattr(self, first) & getattr(self, second)
            if overlap:
                raise ValueError(
                    f"{first} and {second} overlap: {sorted(overlap)}",
                )

        rename_targets = {rename.current_path for rename in self.renamed}
        rename_sources = {rename.previous_path for rename in self.renamed}
        if len(rename_targets) != len(self.renamed):
            raise ValueError("a path cannot be the target of two renames")
        if len(rename_sources) != len(self.renamed):
            raise ValueError("a path cannot be the source of two renames")
        if rename_targets & self.added:
            raise ValueError(
                f"rename targets must not also be added: "
                f"{sorted(rename_targets & self.added)}"
            )
        if rename_sources & self.deleted:
            raise ValueError(
                f"rename sources must not also be deleted: "
                f"{sorted(rename_sources & self.deleted)}"
            )

    # -- derived work sets -------------------------------------------------

    def paths_requiring_reparse(self) -> FrozenSet[str]:
        """Head paths whose content must be parsed.

        Excludes renames, whose content is byte-identical and therefore already
        cached under the same content hash. This exclusion is the practical payoff of
        content addressing: moving a directory of a thousand files costs no parsing.
        """
        return self.added | self.modified

    def paths_to_invalidate(self) -> FrozenSet[str]:
        """Base paths whose previously derived facts are no longer valid.

        For a rename this is the *previous* path, because that is where the stale
        facts are recorded.
        """
        return (
            self.modified
            | self.deleted
            | frozenset(rename.previous_path for rename in self.renamed)
        )

    def head_paths_touched(self) -> FrozenSet[str]:
        """Every head path this change set affects, renames included.

        Distinct from :meth:`paths_requiring_reparse`: a renamed path is touched,
        because its manifest entry moves, but it needs no reparse.
        """
        return (
            self.added
            | self.modified
            | frozenset(rename.current_path for rename in self.renamed)
        )

    # -- aggregates -------------------------------------------------------

    @property
    def is_empty(self) -> bool:
        """Whether the two commits have identical trees."""
        return not (self.added or self.modified or self.deleted or self.renamed)

    @property
    def is_full_rebuild(self) -> bool:
        """Whether there is no base commit, making every path an addition."""
        return self.base_sha is None

    @property
    def total(self) -> int:
        """Number of affected paths, counting a rename once."""
        return (
            len(self.added) + len(self.modified) + len(self.deleted) + len(self.renamed)
        )

    def counts(self) -> Mapping[str, int]:
        """Count per category, omitting empty categories.

        Suitable directly as a progress summary and as bounded-cardinality metric
        labels.
        """
        counts: Dict[str, int] = {
            "added": len(self.added),
            "modified": len(self.modified),
            "deleted": len(self.deleted),
            "renamed": len(self.renamed),
        }
        return {name: value for name, value in counts.items() if value}

    def __str__(self) -> str:
        base = self.base_sha[:12] if self.base_sha else "(none)"
        rendered = ", ".join(
            f"{name}={value}" for name, value in sorted(self.counts().items())
        )
        return f"changeset({base} -> {self.head_sha[:12]}: {rendered or 'no changes'})"
