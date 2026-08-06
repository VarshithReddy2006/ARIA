"""Commit entity.

Implements Twin Spec section 3.2, entity ``Commit``. Two properties of that
specification drive the whole design of this module.

Immutability of facts
    "Never updated after reaching ``queryable``." Facts are therefore separated
    from the mutable index state, and :meth:`Commit.facts_fingerprint` produces a
    digest over exactly the immutable fields. The persistence adapter compares
    that digest on write and refuses a rewrite, which turns a specification
    sentence into an enforced invariant.

Self-reported coverage
    ``coverage`` is described as "the Twin's self-report". It is optional and
    ``None`` until measured, because reporting zero coverage and reporting
    unmeasured coverage are different statements and conflating them would
    violate PRD principle P11.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import ClassVar, Mapping, Optional, Tuple

from ria.domain.enums import (
    COMMIT_INDEX_TRANSITIONS,
    CommitIndexState,
    assert_transition,
)
from ria.domain.errors import ImmutableFactViolationError
from ria.domain.identity import CommitId, CommitSha, RepositoryId
from ria.domain.models.person import PersonRef

__all__ = ["ChangeStats", "LanguageCoverage", "CommitCoverage", "CommitRef", "Commit"]


@dataclass(frozen=True)
class ChangeStats:
    """Line and file counts for a commit relative to its first parent.

    Attributes:
        files_changed: Number of files added, modified or deleted.
        insertions: Lines added.
        deletions: Lines removed.
    """

    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0

    def __post_init__(self) -> None:
        for name in ("files_changed", "insertions", "deletions"):
            value = getattr(self, name)
            if value < 0:
                raise ValueError(f"{name} must be non-negative, got {value}")

    @property
    def churn(self) -> int:
        """Total lines touched, the standard churn measure."""
        return self.insertions + self.deletions


@dataclass(frozen=True)
class LanguageCoverage:
    """Coverage achieved for one language within a commit.

    Attributes:
        language: Canonical language name.
        files_total: Files of this language present in the tree.
        files_parsed: Files of this language successfully parsed.
        symbols_total: Symbols extracted. ``None`` until Milestone 4.
        symbols_resolved: Symbols bound to a definition. ``None`` until
            Milestone 4.
        exact_edges: Relations with ``method=exact``. ``None`` until Milestone 5.
        total_edges: Relations of any method. ``None`` until Milestone 5.
    """

    language: str
    files_total: int
    files_parsed: int
    symbols_total: Optional[int] = None
    symbols_resolved: Optional[int] = None
    exact_edges: Optional[int] = None
    total_edges: Optional[int] = None

    def __post_init__(self) -> None:
        if not self.language:
            raise ValueError("language must be non-empty")
        if self.files_total < 0 or self.files_parsed < 0:
            raise ValueError("file counts must be non-negative")
        if self.files_parsed > self.files_total:
            raise ValueError(
                f"files_parsed ({self.files_parsed}) cannot exceed "
                f"files_total ({self.files_total})"
            )

    @property
    def files_parsed_pct(self) -> float:
        """Percentage of this language's files that were parsed."""
        if self.files_total == 0:
            return 0.0
        return 100.0 * self.files_parsed / self.files_total


@dataclass(frozen=True)
class CommitCoverage:
    """What the index actually understands about a commit.

    Returned in the envelope of every query response (Twin Spec section 7.1) so
    that a consumer can decide whether to act on an answer, verify it, or
    escalate. Twin Spec section 9 states the rule this class exists to serve: "a
    Twin that cannot state what it does not know is not usable by an autonomous
    agent."

    Attributes:
        files_total: Files in the commit tree.
        files_eligible: Files eligible for parsing after classification.
        files_parsed: Files successfully parsed, fully or partially.
        symbols_total: Symbols extracted. ``None`` until Milestone 4.
        symbols_resolved: Symbols bound to a definition. ``None`` until
            Milestone 4.
        exact_edges: Relations with ``method=exact``. ``None`` until Milestone 5.
        total_edges: Relations of any method. ``None`` until Milestone 5.
        by_language: Per-language breakdown.
    """

    files_total: int
    files_eligible: int
    files_parsed: int
    symbols_total: Optional[int] = None
    symbols_resolved: Optional[int] = None
    exact_edges: Optional[int] = None
    total_edges: Optional[int] = None
    by_language: Tuple[LanguageCoverage, ...] = ()

    def __post_init__(self) -> None:
        for name in ("files_total", "files_eligible", "files_parsed"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.files_eligible > self.files_total:
            raise ValueError("files_eligible cannot exceed files_total")
        if self.files_parsed > self.files_eligible:
            raise ValueError("files_parsed cannot exceed files_eligible")
        object.__setattr__(self, "by_language", tuple(self.by_language))

    @property
    def files_parsed_pct(self) -> float:
        """Percentage of eligible files that were parsed."""
        if self.files_eligible == 0:
            return 0.0
        return 100.0 * self.files_parsed / self.files_eligible

    @property
    def symbols_resolved_pct(self) -> Optional[float]:
        """Percentage of symbols bound to a definition, or ``None`` if unmeasured."""
        if self.symbols_total is None or self.symbols_resolved is None:
            return None
        if self.symbols_total == 0:
            return 0.0
        return 100.0 * self.symbols_resolved / self.symbols_total

    @property
    def exact_edge_pct(self) -> Optional[float]:
        """Percentage of relations resolved exactly, or ``None`` if unmeasured.

        This is the single best proxy for index precision (PRD section 12.2) and
        the figure that gates Milestone 4 acceptance.
        """
        if self.total_edges is None or self.exact_edges is None:
            return None
        if self.total_edges == 0:
            return 0.0
        return 100.0 * self.exact_edges / self.total_edges

    def language_index(self) -> Mapping[str, LanguageCoverage]:
        """Index the per-language breakdown by canonical language name."""
        return {entry.language: entry for entry in self.by_language}


@dataclass(frozen=True)
class CommitRef:
    """A resolved pointer from a ref expression to a commit.

    Produced by ref resolution. Records what was asked for alongside what it
    resolved to, so that a cached or logged result remains interpretable.

    Attributes:
        sha: The commit the ref resolved to.
        ref: The ref expression that was resolved, for example ``main`` or
            ``v1.2.0``. ``None`` when a full SHA was supplied directly.
        is_symbolic: Whether ``ref`` was a symbolic name rather than an object
            name. A symbolic ref may resolve differently later; a SHA may not.
    """

    sha: CommitSha
    ref: Optional[str] = None
    is_symbolic: bool = False

    def __str__(self) -> str:
        return f"{self.ref}@{self.sha.short}" if self.ref else self.sha.short


@dataclass(frozen=True)
class Commit:
    """A commit and its index lifecycle state.

    Attributes:
        repository_id: Owning repository.
        sha: Git object name of the commit.
        parents: Parent object names in git order. More than one parent means the
            commit is a merge.
        author: Signature of the person who wrote the change.
        committer: Signature of the person who applied it.
        authored_at: When the change was written.
        committed_at: When the change was applied.
        message: Full commit message.
        tree_hash: Git tree object name.
        change_stats: Line and file counts relative to the first parent.
        index_state: Position in the index lifecycle.
        coverage: What the index understands about this commit. ``None`` until
            measured.
        indexed_at: When indexing completed.
        failure_reason: Why indexing failed. Mandatory when ``index_state`` is
            ``FAILED``.
    """

    repository_id: RepositoryId
    sha: CommitSha
    parents: Tuple[CommitSha, ...]
    author: PersonRef
    committer: PersonRef
    authored_at: datetime
    committed_at: datetime
    message: str
    tree_hash: str
    change_stats: ChangeStats = field(default_factory=ChangeStats)
    index_state: CommitIndexState = CommitIndexState.DISCOVERED
    coverage: Optional[CommitCoverage] = None
    indexed_at: Optional[datetime] = None
    failure_reason: Optional[str] = None

    #: Fields that constitute immutable facts about the commit. Everything else
    #: describes our processing of it and may change. Declared as a
    #: :data:`~typing.ClassVar` so that it is not a dataclass field.
    FACT_FIELDS: ClassVar[Tuple[str, ...]] = (
        "repository_id",
        "sha",
        "parents",
        "author",
        "committer",
        "authored_at",
        "committed_at",
        "message",
        "tree_hash",
    )

    def __post_init__(self) -> None:
        if not self.tree_hash:
            raise ValueError("tree_hash must be non-empty")
        if self.index_state is CommitIndexState.FAILED and not self.failure_reason:
            raise ValueError("failure_reason is mandatory when index_state is FAILED")
        if self.index_state is not CommitIndexState.FAILED and self.failure_reason:
            raise ValueError(
                "failure_reason must be absent unless index_state is FAILED"
            )
        object.__setattr__(self, "parents", tuple(self.parents))

    # -- identity ---------------------------------------------------------

    @property
    def commit_id(self) -> CommitId:
        """Composite primary key of this commit."""
        return CommitId(repository_id=self.repository_id, sha=self.sha)

    @property
    def is_merge(self) -> bool:
        """Whether the commit has more than one parent."""
        return len(self.parents) > 1

    @property
    def is_root(self) -> bool:
        """Whether the commit has no parents."""
        return not self.parents

    @property
    def first_parent(self) -> Optional[CommitSha]:
        """First parent, which defines the mainline for diff purposes."""
        return self.parents[0] if self.parents else None

    @property
    def subject(self) -> str:
        """First line of the commit message."""
        return self.message.split("\n", 1)[0].strip()

    # -- immutability ------------------------------------------------------

    def facts_fingerprint(self) -> str:
        """Digest over the immutable factual fields of this commit.

        The persistence adapter stores this value and compares it on every write.
        A mismatch on a commit whose facts are frozen raises
        :class:`~ria.domain.errors.ImmutableFactViolationError`, which enforces
        the specification sentence "Never updated after reaching ``queryable``".

        Returns:
            Hexadecimal SHA-256 digest of the canonical fact representation.
        """
        digest = hashlib.sha256()
        for name in self.FACT_FIELDS:
            value = getattr(self, name)
            if isinstance(value, tuple):
                rendered = ",".join(str(item) for item in value)
            elif isinstance(value, datetime):
                rendered = value.isoformat()
            else:
                rendered = str(value)
            digest.update(name.encode("utf-8"))
            digest.update(b"\x00")
            digest.update(rendered.encode("utf-8"))
            digest.update(b"\x1e")
        return digest.hexdigest()

    def assert_facts_match(self, expected_fingerprint: str) -> None:
        """Verify that this commit's facts match a previously stored digest.

        Args:
            expected_fingerprint: Digest recorded when the commit was first
                persisted.

        Raises:
            ImmutableFactViolationError: If the digests differ.
        """
        actual = self.facts_fingerprint()
        if actual != expected_fingerprint:
            raise ImmutableFactViolationError(
                "commit facts may not be rewritten once the commit is queryable",
                {
                    "repository_id": str(self.repository_id),
                    "sha": str(self.sha),
                    "expected_fingerprint": expected_fingerprint,
                    "actual_fingerprint": actual,
                },
            )

    # -- transitions -------------------------------------------------------

    def transition_to(
        self,
        state: CommitIndexState,
        *,
        now: Optional[datetime] = None,
        failure_reason: Optional[str] = None,
        coverage: Optional[CommitCoverage] = None,
    ) -> "Commit":
        """Return a copy of this commit in a new index state.

        Args:
            state: Target index state.
            now: Timestamp recorded as ``indexed_at`` when the target state is
                :attr:`~ria.domain.enums.CommitIndexState.QUERYABLE`. Required
                for that transition.
            failure_reason: Required when the target state is
                :attr:`~ria.domain.enums.CommitIndexState.FAILED`.
            coverage: Coverage measured during the build. Only accepted on the
                transition to ``QUERYABLE``, because coverage that does not
                describe a completed build is not a meaningful statement.

        Returns:
            A new :class:`Commit` in the requested state.

        Raises:
            IllegalStateTransitionError: If the transition is not permitted.
            ValueError: If required arguments for the target state are missing.
        """
        assert_transition("Commit", self.index_state, state, COMMIT_INDEX_TRANSITIONS)

        if state is CommitIndexState.QUERYABLE:
            if now is None:
                raise ValueError("now is required when transitioning to QUERYABLE")
            return replace(
                self,
                index_state=state,
                indexed_at=now,
                coverage=coverage if coverage is not None else self.coverage,
                failure_reason=None,
            )

        if state is CommitIndexState.FAILED:
            if not failure_reason:
                raise ValueError(
                    "failure_reason is required when transitioning to FAILED"
                )
            return replace(self, index_state=state, failure_reason=failure_reason)

        if coverage is not None:
            raise ValueError(
                "coverage may only be recorded when transitioning to QUERYABLE"
            )

        return replace(self, index_state=state, failure_reason=None)

    def mark_orphaned(self) -> "Commit":
        """Return a copy marked orphaned after an upstream history rewrite.

        Twin Spec section 3.2 requires that orphaned commits retain their facts:
        deleting them "would silently rewrite our own history and invalidate past
        answers we have already given". This method therefore changes only the
        index state.
        """
        return self.transition_to(CommitIndexState.ORPHANED)
