"""Commit resolution use case.

Resolves a ref expression to a commit and records that commit's immutable facts.

Why resolution is its own use case
----------------------------------
Twin Spec section 3.1, Rule 2 requires every fact to be keyed by a commit, and PRD
principle P5 states that an unversioned answer about code is a guess about which
code. Resolution is therefore the first step of every operation in the system, not
a detail of ingestion. Isolating it means Milestone 2's ingestion pipeline,
Milestone 5's graph queries and the eventual query gateway all obtain a commit the
same way, with the same guarantees.

What this use case guarantees
-----------------------------
* A returned :class:`~ria.domain.models.commit.CommitRef` always holds a full
  object name. Abbreviated SHAs are expanded by the git adapter, so no ambiguous
  identity enters the system.
* A symbolic ref is marked as such, because a branch name may resolve differently
  later while an object name may not — information a cache or an audit needs.
* Recording a commit is idempotent, so re-resolving the same ref performs no
  further writes and cannot fail (SDD section 4: "Every task idempotent and
  resumable").
* Facts already recorded for a queryable commit are never rewritten; an attempt
  raises rather than silently altering history.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from ria.domain.enums import CommitIndexState
from ria.domain.errors import CommitNotFoundError, RepositoryNotFoundError
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.branch import Branch
from ria.domain.models.commit import Commit, CommitRef
from ria.domain.models.person import PersonRef
from ria.observability.logging import get_logger, log_context
from ria.ports.clock import Clock
from ria.ports.git_client import GitClient, RawCommit
from ria.ports.metrics import MetricsSink
from ria.ports.unit_of_work import UnitOfWorkFactory

__all__ = ["ResolvedCommit", "CommitResolver"]

_LOGGER = get_logger(__name__)

#: Metric names emitted by this use case.
_METRIC_RESOLVED = "ria_commit_resolved_total"
_METRIC_RECORDED = "ria_commit_recorded_total"
_METRIC_OPERATION_SECONDS = "ria_commit_operation_seconds"


@dataclass(frozen=True)
class ResolvedCommit:
    """Outcome of resolving a ref and recording its commit.

    Attributes:
        reference: The resolved pointer, retaining what was asked for.
        commit: The recorded commit.
        was_already_recorded: Whether the commit was already known. Distinguishing
            this from a first observation lets a caller skip work without having to
            compare states itself.
    """

    reference: CommitRef
    commit: Commit
    was_already_recorded: bool

    @property
    def sha(self) -> CommitSha:
        """Object name of the resolved commit."""
        return self.commit.sha


class CommitResolver:
    """Resolves refs to commits and records their facts.

    Args:
        git: Read-only git access.
        unit_of_work_factory: Creates a transaction per operation.
        clock: Source of timestamps.
        metrics: Sink for operation counts and durations.
    """

    def __init__(
        self,
        git: GitClient,
        unit_of_work_factory: UnitOfWorkFactory,
        clock: Clock,
        metrics: MetricsSink,
    ) -> None:
        self._git = git
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock
        self._metrics = metrics

    # -- resolution -------------------------------------------------------

    def resolve(self, repository_path: Path, ref: str) -> CommitRef:
        """Resolve a ref expression to a commit pointer without recording anything.

        Args:
            repository_path: Path of the git directory.
            ref: Branch, tag, full or abbreviated SHA, or any expression git
                accepts.

        Returns:
            The resolved pointer.

        Raises:
            ValueError: If the ref expression is empty once normalised.
            RefNotFoundError: If the ref does not resolve to a commit.
            GitCommandError: If the git invocation fails.
        """
        # Normalise before the git call, not after. Passing the raw value to git
        # and comparing against a stripped copy would send an unusable expression
        # downstream while reporting symbolic status against a different string.
        expression = (ref or "").strip()
        if not expression:
            raise ValueError("ref expression must be non-empty")

        with self._metrics.timer(
            _METRIC_OPERATION_SECONDS, labels={"operation": "resolve"}
        ):
            sha = CommitSha(self._git.resolve_ref(repository_path, expression))
        # A full object name is not symbolic; anything else may resolve
        # differently in future, including an abbreviated SHA, which is why the
        # comparison is against the expanded value.
        is_symbolic = expression != sha.value
        self._metrics.increment(
            _METRIC_RESOLVED, labels={"symbolic": "true" if is_symbolic else "false"}
        )
        return CommitRef(sha=sha, ref=expression, is_symbolic=is_symbolic)

    def resolve_and_record(
        self, repository_id: RepositoryId, repository_path: Path, ref: str
    ) -> ResolvedCommit:
        """Resolve a ref and record the resulting commit's facts.

        Args:
            repository_id: Repository the commit belongs to.
            repository_path: Path of the git directory.
            ref: Ref expression to resolve.

        Returns:
            The resolution outcome.

        Raises:
            RepositoryNotFoundError: If the repository is not registered.
            RefNotFoundError: If the ref does not resolve to a commit.
            ImmutableFactViolationError: If the commit is already queryable and the
                re-observed facts differ from those recorded.
            StorageError: If the write fails.
        """
        reference = self.resolve(repository_path, ref)
        with log_context(repository_id=str(repository_id), commit=reference.sha.short):
            with self._metrics.timer(
                _METRIC_OPERATION_SECONDS, labels={"operation": "resolve_and_record"}
            ):
                raw = self._git.read_commit(repository_path, reference.sha.value)
                commit = self._to_commit(repository_id, raw)
                with self._unit_of_work_factory() as unit_of_work:
                    if unit_of_work.repositories.get(repository_id) is None:
                        raise RepositoryNotFoundError(
                            "repository is not registered",
                            {"repository_id": str(repository_id)},
                        )
                    existing = unit_of_work.commits.get(repository_id, commit.sha)
                    if existing is not None:
                        # Facts are re-observed but not rewritten. The commit store
                        # verifies the fingerprint, so a mismatch raises rather
                        # than overwriting recorded history.
                        unit_of_work.commits.upsert(existing)
                        unit_of_work.commit()
                        self._metrics.increment(
                            _METRIC_RECORDED, labels={"outcome": "already_recorded"}
                        )
                        return ResolvedCommit(
                            reference=reference,
                            commit=existing,
                            was_already_recorded=True,
                        )
                    unit_of_work.commits.add(commit)
                    unit_of_work.commit()

            self._metrics.increment(_METRIC_RECORDED, labels={"outcome": "recorded"})
            _LOGGER.info(
                "commit recorded",
                extra={
                    "ref": reference.ref,
                    "parents": len(commit.parents),
                    "is_merge": commit.is_merge,
                },
            )
        return ResolvedCommit(
            reference=reference, commit=commit, was_already_recorded=False
        )

    # -- reads ------------------------------------------------------------

    def get(self, repository_id: RepositoryId, sha: CommitSha) -> Commit:
        """Load a recorded commit.

        Args:
            repository_id: Owning repository.
            sha: Commit object name.

        Returns:
            The commit.

        Raises:
            CommitNotFoundError: If the commit is not recorded.
        """
        with self._unit_of_work_factory() as unit_of_work:
            commit = unit_of_work.commits.get(repository_id, sha)
        if commit is None:
            raise CommitNotFoundError(
                "commit is not recorded",
                {"repository_id": str(repository_id), "sha": str(sha)},
            )
        return commit

    def latest_queryable(self, repository_id: RepositoryId) -> Optional[Commit]:
        """Most recently committed commit that is queryable.

        This is what an unpinned query resolves to: the newest commit whose index is
        complete. A commit that is still being indexed is deliberately invisible,
        per the atomic visibility rule of SDD section 5.1.

        Args:
            repository_id: Owning repository.

        Returns:
            The commit, or ``None`` if none is queryable.
        """
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.commits.latest_queryable(repository_id)

    def pending_work(
        self, repository_id: RepositoryId, *, limit: int = 100
    ) -> Sequence[Commit]:
        """List commits awaiting indexing, oldest committed first.

        History order is the correct processing order: a later commit's incremental
        build reuses the parse cache produced by an earlier one.

        Args:
            repository_id: Owning repository.
            limit: Maximum number of records.

        Returns:
            Commits in the ``PENDING`` state.
        """
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.commits.list_by_state(
                repository_id, CommitIndexState.PENDING, limit=limit
            )

    # -- branches ---------------------------------------------------------

    def record_branches(
        self, repository_id: RepositoryId, repository_path: Path
    ) -> int:
        """Observe every local branch and replace the recorded branch set.

        Replacement rather than merge, because upstream branch deletion can only be
        detected by comparing whole sets. The replacement happens in one transaction
        so no consumer observes an empty branch list.

        Args:
            repository_id: Owning repository.
            repository_path: Path of the git directory.

        Returns:
            Number of branches recorded.

        Raises:
            RepositoryNotFoundError: If the repository is not registered.
            GitCommandError: If the git invocation fails.
            StorageError: If the write fails.
        """
        now = self._clock.now()
        observed = self._git.list_branches(repository_path)
        branches = [
            Branch(
                repository_id=repository_id,
                name=raw.name,
                head_sha=CommitSha(raw.head_sha),
                updated_at=now,
                is_default=raw.is_default,
                last_commit_at=raw.last_commit_at,
            )
            for raw in observed
        ]
        with log_context(repository_id=str(repository_id)):
            with self._metrics.timer(
                _METRIC_OPERATION_SECONDS, labels={"operation": "record_branches"}
            ):
                with self._unit_of_work_factory() as unit_of_work:
                    if unit_of_work.repositories.get(repository_id) is None:
                        raise RepositoryNotFoundError(
                            "repository is not registered",
                            {"repository_id": str(repository_id)},
                        )
                    unit_of_work.branches.replace_all(repository_id, branches)
                    unit_of_work.commit()
            _LOGGER.info("branches recorded", extra={"count": len(branches)})
        return len(branches)

    # -- internals --------------------------------------------------------

    @staticmethod
    def _to_commit(repository_id: RepositoryId, raw: RawCommit) -> Commit:
        """Map a raw git observation onto the commit entity.

        Mapping happens here rather than in the git adapter because git has no
        notion of a repository identifier; pushing that knowledge into the adapter
        would invert the dependency rule of SDD section 2.3.

        The commit enters at :attr:`~ria.domain.enums.CommitIndexState.DISCOVERED`.
        Nothing has been indexed yet, and claiming otherwise would make the commit
        visible to queries before its facts exist.

        Args:
            repository_id: Repository the commit belongs to.
            raw: Git observation.

        Returns:
            The commit entity.
        """
        return Commit(
            repository_id=repository_id,
            sha=CommitSha(raw.sha),
            parents=tuple(CommitSha(parent) for parent in raw.parent_shas),
            author=PersonRef(name=raw.author.name, email=raw.author.email or None),
            committer=PersonRef(
                name=raw.committer.name, email=raw.committer.email or None
            ),
            authored_at=raw.author.timestamp,
            committed_at=raw.committer.timestamp,
            message=raw.message,
            tree_hash=raw.tree_sha,
            index_state=CommitIndexState.DISCOVERED,
        )
