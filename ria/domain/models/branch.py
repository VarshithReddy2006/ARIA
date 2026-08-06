"""Branch entity.

Implements Twin Spec section 3.2, entity ``Branch``. The specification's design
note is the whole point of this module:

    "Branch mutability is confined to a single pointer field. All facts hang off
    immutable commits. This is what makes branch support nearly free: a branch
    query resolves the pointer, then executes an ordinary commit-scoped query."

Accordingly :class:`Branch` carries exactly one mutable value, ``head_sha``, plus
a merge-base cache which is a pure optimisation and may be discarded at any time
without loss of correctness.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Mapping, Optional

from ria.domain.enums import BranchCadence
from ria.domain.identity import CommitSha, RepositoryId

__all__ = ["Branch"]


@dataclass(frozen=True)
class Branch:
    """A named ref pointing at a commit.

    Attributes:
        repository_id: Owning repository.
        name: Branch name without the ``refs/heads/`` prefix.
        head_sha: Commit the branch currently points at. The only value that
            changes over the branch's life.
        is_default: Whether this is the repository's default branch.
        is_protected: Whether the forge marks the branch as protected. Recorded
            because protection is a signal that the branch is release-bearing and
            therefore warrants a denser snapshot cadence.
        last_commit_at: Commit timestamp of the head, used to decide staleness.
        updated_at: When this record last changed.
        merge_base_cache: Cached merge bases against other branches, keyed by
            branch name. Purely an optimisation for diff queries; correctness
            never depends on it.
    """

    repository_id: RepositoryId
    name: str
    head_sha: CommitSha
    updated_at: datetime
    is_default: bool = False
    is_protected: bool = False
    last_commit_at: Optional[datetime] = None
    merge_base_cache: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("branch name must be non-empty")
        if self.name.startswith("refs/"):
            raise ValueError(
                f"branch name must not include a refs/ prefix, got {self.name!r}"
            )
        # Freeze the cache so the entity cannot be mutated through a shared
        # reference held elsewhere.
        object.__setattr__(self, "merge_base_cache", dict(self.merge_base_cache))

    def moved_to(
        self,
        head_sha: CommitSha,
        *,
        now: datetime,
        last_commit_at: Optional[datetime] = None,
    ) -> "Branch":
        """Return a copy pointing at a new head commit.

        Moving the head invalidates every cached merge base, so the cache is
        cleared rather than selectively pruned: a stale merge base would produce
        a silently wrong pull request diff, and clearing is cheap.

        Args:
            head_sha: New head commit.
            now: Timestamp to record as ``updated_at``.
            last_commit_at: Commit timestamp of the new head.

        Returns:
            A new :class:`Branch` with the updated pointer and an empty cache.
        """
        return replace(
            self,
            head_sha=head_sha,
            last_commit_at=last_commit_at
            if last_commit_at is not None
            else self.last_commit_at,
            merge_base_cache={},
            updated_at=now,
        )

    def with_merge_base(self, other_branch: str, merge_base_sha: str) -> "Branch":
        """Return a copy with an additional cached merge base.

        Args:
            other_branch: Name of the branch the merge base was computed against.
            merge_base_sha: The merge base commit.
        """
        cache = dict(self.merge_base_cache)
        cache[other_branch] = merge_base_sha
        return replace(self, merge_base_cache=cache)

    def cadence(
        self,
        policy_cadence_for_default: BranchCadence,
        policy_cadence_for_feature: BranchCadence,
    ) -> BranchCadence:
        """Resolve the snapshot cadence that applies to this branch.

        Args:
            policy_cadence_for_default: Cadence configured for default branches.
            policy_cadence_for_feature: Cadence configured for feature branches.

        Returns:
            The cadence to apply.
        """
        return (
            policy_cadence_for_default
            if self.is_default
            else policy_cadence_for_feature
        )

    def is_stale(self, *, now: datetime, stale_after_days: int) -> bool:
        """Whether the branch has had no activity within the staleness window.

        A branch whose head commit time is unknown is never considered stale,
        because treating unknown as stale would silently stop indexing it.

        Args:
            now: Current time. Must share the awareness of ``last_commit_at``.
            stale_after_days: Window in days from the index policy.

        Returns:
            ``True`` if the branch is stale and should not be indexed.
        """
        if self.is_default or self.last_commit_at is None:
            return False
        age_days = (now - self.last_commit_at).total_seconds() / 86400.0
        return age_days > stale_after_days

    def __str__(self) -> str:
        return f"{self.name}@{self.head_sha.short}"
