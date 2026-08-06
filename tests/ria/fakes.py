"""In-memory port implementations for unit tests.

These live in the test tree, never in the distribution, so that no fake can be
imported by production code by accident.

Each fake is a complete implementation of its port rather than a stub returning
canned values. That matters most for :class:`InMemoryCommitStore`, which reproduces
the fact-immutability enforcement of the SQLite adapter: a fake that skipped the
check would let a unit test pass while the real adapter raised, which is worse
than having no test.

Transaction semantics are modelled too. :class:`InMemoryUnitOfWork` copies the
backing state on entry and publishes it only on :meth:`commit`, so a test that
forgets to commit observes the same rollback behaviour the SQLite adapter provides.
"""

from __future__ import annotations

import io
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import TracebackType
from typing import IO, Dict, Iterator, List, Optional, Sequence, Tuple, Type

from ria.domain.enums import CommitIndexState, JobKind, JobState, RepositoryStatus
from ria.domain.errors import (
    CommitNotFoundError,
    ImmutableFactViolationError,
    JobNotFoundError,
    RefNotFoundError,
    RepositoryAlreadyExistsError,
    RepositoryNotFoundError,
    StorageError,
)
from ria.domain.identity import CommitSha, Moniker, RepositoryId
from ria.domain.models.branch import Branch
from ria.domain.models.commit import Commit
from ria.domain.models.file_unit import FileUnit
from ria.domain.models.job import Job, JobId
from ria.domain.models.repository import Repository
from ria.ports.git_client import (
    GitVersion,
    RawBranch,
    RawCommit,
    RawCommitSummary,
    RawSignature,
    RawTreeEntry,
)

__all__ = [
    "FrozenClock",
    "FakeGitClient",
    "FakeState",
    "InMemoryRepositoryStore",
    "InMemoryCommitStore",
    "InMemoryBranchStore",
    "InMemoryFileUnitStore",
    "InMemoryJobStore",
    "InMemoryUnitOfWork",
    "InMemoryUnitOfWorkFactory",
]


class FrozenClock:
    """Clock that returns a fixed instant, advanced only on request.

    Satisfies :class:`~ria.ports.clock.Clock`. Deterministic timestamps let a test
    assert exact equality on ``updated_at`` instead of asserting a range, which is
    the difference between a test that detects a bug and one that tolerates it.
    """

    def __init__(self, start: Optional[datetime] = None) -> None:
        self._now = start or datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        """Return the current fixed instant."""
        return self._now

    def advance(self, seconds: float = 1.0) -> datetime:
        """Move the clock forward.

        Args:
            seconds: Seconds to advance by.

        Returns:
            The new instant.
        """
        self._now = self._now + timedelta(seconds=seconds)
        return self._now


class FakeGitClient:
    """Scripted git client.

    Satisfies :class:`~ria.ports.git_client.GitClient`. Every response is supplied
    by the test, so a use-case test never depends on a real repository's contents
    or on git being installed.

    Args:
        refs: Mapping from ref expression to full object name. Full object names
            present as keys resolve to themselves.
        commits: Mapping from object name to commit metadata.
        branches: Branches reported by :meth:`list_branches`.
        trees: Mapping from commit object name to its tree entries.
        blobs: Mapping from blob object name to content.
    """

    def __init__(
        self,
        *,
        refs: Optional[Dict[str, str]] = None,
        commits: Optional[Dict[str, RawCommit]] = None,
        branches: Optional[Sequence[RawBranch]] = None,
        trees: Optional[Dict[str, Sequence[RawTreeEntry]]] = None,
        blobs: Optional[Dict[str, bytes]] = None,
        history: Optional[Dict[str, Sequence[RawCommitSummary]]] = None,
    ) -> None:
        self.refs: Dict[str, str] = dict(refs or {})
        self.commits: Dict[str, RawCommit] = dict(commits or {})
        self.branches: List[RawBranch] = list(branches or [])
        self.trees: Dict[str, Sequence[RawTreeEntry]] = dict(trees or {})
        self.blobs: Dict[str, bytes] = dict(blobs or {})
        self.history: Dict[str, Sequence[RawCommitSummary]] = dict(history or {})
        #: Recorded calls, so a test can assert that git was consulted once.
        self.calls: List[Tuple[str, str]] = []
        #: Mirrors this client was asked to create, so a test can assert acquisition
        #: happened without a filesystem.
        self.cloned: List[Tuple[str, Path]] = []
        #: Mirrors this client was asked to refresh.
        self.fetched: List[Path] = []

    # -- GitClient --------------------------------------------------------

    def version(self) -> GitVersion:
        """Return a fixed version."""
        return GitVersion(raw="git version 2.44.0", major=2, minor=44, patch=0)

    def resolve_ref(self, repository_path: Path, ref: str) -> str:
        """Resolve a scripted ref to a full object name.

        Raises:
            RefNotFoundError: If the ref is not scripted.
        """
        self.calls.append(("resolve_ref", ref))
        if ref in self.refs:
            return self.refs[ref]
        if ref in self.commits:
            return ref
        raise RefNotFoundError("ref did not resolve", {"ref": ref})

    def read_commit(self, repository_path: Path, sha: str) -> RawCommit:
        """Return scripted commit metadata.

        Raises:
            RefNotFoundError: If the commit is not scripted.
        """
        self.calls.append(("read_commit", sha))
        commit = self.commits.get(sha)
        if commit is None:
            raise RefNotFoundError("commit not found", {"sha": sha})
        return commit

    def list_branches(self, repository_path: Path) -> Sequence[RawBranch]:
        """Return the scripted branch set."""
        self.calls.append(("list_branches", str(repository_path)))
        return tuple(self.branches)

    def detect_default_branch(self, repository_path: Path) -> str:
        """Return the name of the scripted default branch.

        Raises:
            RefNotFoundError: If no branch is marked default.
        """
        for branch in self.branches:
            if branch.is_default:
                return branch.name
        raise RefNotFoundError("no default branch", {"path": str(repository_path)})

    def list_tree(self, repository_path: Path, sha: str) -> Sequence[RawTreeEntry]:
        """Return the scripted tree of a commit."""
        self.calls.append(("list_tree", sha))
        return tuple(self.trees.get(sha, ()))

    def read_blob(self, repository_path: Path, blob_sha: str) -> bytes:
        """Return scripted blob content.

        Raises:
            RefNotFoundError: If the blob is not scripted.
        """
        self.calls.append(("read_blob", blob_sha))
        if blob_sha not in self.blobs:
            raise RefNotFoundError("blob not found", {"blob_sha": blob_sha})
        return self.blobs[blob_sha]

    def count_lines(self, data: bytes) -> Optional[int]:
        """Count lines, treating a NUL byte as evidence of binary content."""
        if b"\x00" in data:
            return None
        if not data:
            return 0
        return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)

    @contextmanager
    def open_blob(self, repository_path: Path, blob_sha: str) -> Iterator[IO[bytes]]:
        """Open scripted blob content as a managed binary stream.

        Raises:
            RefNotFoundError: If the blob is not scripted.
        """
        self.calls.append(("open_blob", blob_sha))
        if blob_sha not in self.blobs:
            raise RefNotFoundError("blob not found", {"blob_sha": blob_sha})
        stream = io.BytesIO(self.blobs[blob_sha])
        try:
            yield stream
        finally:
            stream.close()

    def clone_mirror(self, origin_url: str, destination: Path) -> None:
        """Record a clone without touching the filesystem."""
        self.calls.append(("clone_mirror", origin_url))
        self.cloned.append((origin_url, destination))

    def fetch(self, repository_path: Path, *, prune: bool = True) -> None:
        """Record a fetch without contacting an origin."""
        self.calls.append(("fetch", str(repository_path)))
        self.fetched.append(repository_path)

    def list_commits(
        self,
        repository_path: Path,
        ref: str,
        *,
        limit: int,
        since: Optional[datetime] = None,
    ) -> Sequence[RawCommitSummary]:
        """Walk the scripted history from a ref, newest first.

        The walk is scripted per ref rather than derived from the parent chain, so a
        test can present any history shape without constructing a consistent graph.

        Raises:
            RefNotFoundError: If the ref is not scripted.
        """
        self.calls.append(("list_commits", ref))
        if ref in self.history:
            summaries = self.history[ref]
        else:
            resolved = self.resolve_ref(repository_path, ref)
            summaries = self.history.get(resolved, ())
        if since is not None:
            summaries = tuple(
                summary for summary in summaries if summary.committed_at >= since
            )
        return tuple(summaries[:limit])

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def commit_fixture(
        sha: str,
        *,
        parents: Sequence[str] = (),
        message: str = "change",
        when: Optional[datetime] = None,
        tree_sha: str = "t" * 40,
        author: str = "Ada Lovelace",
        email: str = "ada@example.com",
    ) -> RawCommit:
        """Build a :class:`~ria.ports.git_client.RawCommit` for a test.

        Args:
            sha: Full object name.
            parents: Parent object names.
            message: Commit message.
            when: Signature timestamp.
            tree_sha: Tree object name.
            author: Author display name.
            email: Author email.

        Returns:
            A raw commit suitable for scripting.
        """
        moment = when or datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
        signature = RawSignature(name=author, email=email, timestamp=moment)
        return RawCommit(
            sha=sha,
            parent_shas=tuple(parents),
            tree_sha=tree_sha,
            author=signature,
            committer=signature,
            message=message,
        )


class FakeState:
    """Shared backing state for the in-memory stores.

    Holds the committed contents of the fake database. A unit of work reads a copy
    and writes back only on commit, which reproduces transactional isolation.
    """

    def __init__(self) -> None:
        self.repositories: Dict[str, Repository] = {}
        self.commits: Dict[Tuple[str, str], Commit] = {}
        self.fingerprints: Dict[Tuple[str, str], str] = {}
        self.branches: Dict[Tuple[str, str], Branch] = {}
        self.file_units: Dict[Tuple[str, str, str], FileUnit] = {}
        self.jobs: Dict[str, Job] = {}

    def snapshot(self) -> "FakeState":
        """Return a shallow copy suitable for use inside one transaction."""
        clone = FakeState()
        clone.repositories = dict(self.repositories)
        clone.commits = dict(self.commits)
        clone.fingerprints = dict(self.fingerprints)
        clone.branches = dict(self.branches)
        clone.file_units = dict(self.file_units)
        clone.jobs = dict(self.jobs)
        return clone

    def adopt(self, other: "FakeState") -> None:
        """Replace this state's contents with another's.

        Args:
            other: State to adopt, normally a committed transaction's snapshot.
        """
        self.repositories = dict(other.repositories)
        self.commits = dict(other.commits)
        self.fingerprints = dict(other.fingerprints)
        self.branches = dict(other.branches)
        self.file_units = dict(other.file_units)
        self.jobs = dict(other.jobs)


class InMemoryRepositoryStore:
    """In-memory :class:`~ria.ports.repositories.RepositoryStore`."""

    def __init__(self, state: FakeState) -> None:
        self._state = state

    def add(self, repository: Repository) -> None:
        """Insert a repository, rejecting a duplicate identifier or moniker."""
        key = str(repository.repository_id)
        if key in self._state.repositories:
            raise RepositoryAlreadyExistsError(
                "repository id already exists", {"repository_id": key}
            )
        if any(
            existing.moniker == repository.moniker
            for existing in self._state.repositories.values()
        ):
            raise RepositoryAlreadyExistsError(
                "moniker already registered", {"moniker": str(repository.moniker)}
            )
        self._state.repositories[key] = repository

    def save(self, repository: Repository) -> None:
        """Update an existing repository."""
        key = str(repository.repository_id)
        if key not in self._state.repositories:
            raise RepositoryNotFoundError(
                "repository not found", {"repository_id": key}
            )
        self._state.repositories[key] = repository

    def get(self, repository_id: RepositoryId) -> Optional[Repository]:
        """Load a repository by identifier."""
        return self._state.repositories.get(str(repository_id))

    def get_by_moniker(self, moniker: Moniker) -> Optional[Repository]:
        """Load a repository by moniker."""
        for repository in self._state.repositories.values():
            if repository.moniker == moniker:
                return repository
        return None

    def list(
        self,
        *,
        tenant_id: Optional[str] = None,
        status: Optional[RepositoryStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[Repository]:
        """List repositories ordered by moniker ascending."""
        matches = [
            repository
            for repository in self._state.repositories.values()
            if (tenant_id is None or repository.tenant_id == tenant_id)
            and (status is None or repository.status is status)
        ]
        matches.sort(key=lambda repository: str(repository.moniker))
        return tuple(matches[offset : offset + limit])

    def count(
        self,
        *,
        tenant_id: Optional[str] = None,
        status: Optional[RepositoryStatus] = None,
    ) -> int:
        """Count repositories matching a filter."""
        return len(self.list(tenant_id=tenant_id, status=status, limit=1_000_000))

    def delete(self, repository_id: RepositoryId) -> bool:
        """Delete a repository and cascade to its owned entities."""
        key = str(repository_id)
        if key not in self._state.repositories:
            return False
        del self._state.repositories[key]
        for commit_key in [k for k in self._state.commits if k[0] == key]:
            del self._state.commits[commit_key]
            self._state.fingerprints.pop(commit_key, None)
        for branch_key in [k for k in self._state.branches if k[0] == key]:
            del self._state.branches[branch_key]
        for unit_key in [k for k in self._state.file_units if k[0] == key]:
            del self._state.file_units[unit_key]
        return True


class InMemoryCommitStore:
    """In-memory :class:`~ria.ports.repositories.CommitStore`.

    Reproduces the fact-immutability enforcement of the SQLite adapter so that a
    unit test cannot pass where the real adapter would raise.
    """

    def __init__(self, state: FakeState) -> None:
        self._state = state

    def add(self, commit: Commit) -> None:
        """Insert a commit, rejecting a duplicate identity."""
        key = self._key(commit.repository_id, commit.sha)
        if key in self._state.commits:
            raise StorageError("commit already exists", {"sha": str(commit.sha)})
        self._state.commits[key] = commit
        self._state.fingerprints[key] = commit.facts_fingerprint()

    def save(self, commit: Commit) -> None:
        """Update a commit, refusing to rewrite frozen facts."""
        key = self._key(commit.repository_id, commit.sha)
        existing = self._state.commits.get(key)
        if existing is None:
            raise CommitNotFoundError("commit not recorded", {"sha": str(commit.sha)})
        self._assert_facts_unchanged(commit, existing, key)
        self._state.commits[key] = commit

    def upsert(self, commit: Commit) -> None:
        """Insert or update a commit idempotently."""
        key = self._key(commit.repository_id, commit.sha)
        if key not in self._state.commits:
            self.add(commit)
            return
        self.save(commit)

    def get(self, repository_id: RepositoryId, sha: CommitSha) -> Optional[Commit]:
        """Load one commit."""
        return self._state.commits.get(self._key(repository_id, sha))

    def exists(self, repository_id: RepositoryId, sha: CommitSha) -> bool:
        """Whether a commit is recorded."""
        return self._key(repository_id, sha) in self._state.commits

    def list_by_state(
        self, repository_id: RepositoryId, state: CommitIndexState, *, limit: int = 100
    ) -> Sequence[Commit]:
        """List commits in a state, oldest committed first."""
        matches = [
            commit
            for (repo, _), commit in self._state.commits.items()
            if repo == str(repository_id) and commit.index_state is state
        ]
        matches.sort(key=lambda commit: (commit.committed_at, str(commit.sha)))
        return tuple(matches[:limit])

    def latest_queryable(self, repository_id: RepositoryId) -> Optional[Commit]:
        """Most recently committed queryable commit."""
        candidates = self.list_by_state(
            repository_id, CommitIndexState.QUERYABLE, limit=1_000_000
        )
        return candidates[-1] if candidates else None

    def count_by_state(self, repository_id: RepositoryId) -> Dict[str, int]:
        """Count commits per index state."""
        counts: Dict[str, int] = {}
        for (repo, _), commit in self._state.commits.items():
            if repo != str(repository_id):
                continue
            key = commit.index_state.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    def delete_by_repository(self, repository_id: RepositoryId) -> int:
        """Delete every commit of a repository."""
        keys = [key for key in self._state.commits if key[0] == str(repository_id)]
        for key in keys:
            del self._state.commits[key]
            self._state.fingerprints.pop(key, None)
        return len(keys)

    @staticmethod
    def _key(repository_id: RepositoryId, sha: CommitSha) -> Tuple[str, str]:
        """Build the composite storage key of a commit."""
        return (str(repository_id), str(sha))

    def _assert_facts_unchanged(
        self, commit: Commit, existing: Commit, key: Tuple[str, str]
    ) -> None:
        """Refuse a write that would rewrite frozen facts."""
        if existing.index_state.facts_are_frozen:
            recorded = self._state.fingerprints.get(key)
            if recorded is not None and commit.facts_fingerprint() != recorded:
                raise ImmutableFactViolationError(
                    "commit facts may not be rewritten",
                    {"sha": str(commit.sha)},
                )


class InMemoryBranchStore:
    """In-memory :class:`~ria.ports.repositories.BranchStore`."""

    def __init__(self, state: FakeState) -> None:
        self._state = state

    def upsert(self, branch: Branch) -> None:
        """Insert or update a branch, enforcing a single default."""
        if branch.is_default:
            for key, existing in list(self._state.branches.items()):
                if (
                    key[0] == str(branch.repository_id)
                    and existing.is_default
                    and existing.name != branch.name
                ):
                    raise StorageError(
                        "repository already has a default branch",
                        {"existing": existing.name, "incoming": branch.name},
                    )
        self._state.branches[(str(branch.repository_id), branch.name)] = branch

    def get(self, repository_id: RepositoryId, name: str) -> Optional[Branch]:
        """Load one branch by name."""
        return self._state.branches.get((str(repository_id), name))

    def get_default(self, repository_id: RepositoryId) -> Optional[Branch]:
        """Load the default branch."""
        for key, branch in self._state.branches.items():
            if key[0] == str(repository_id) and branch.is_default:
                return branch
        return None

    def list(self, repository_id: RepositoryId) -> Sequence[Branch]:
        """List branches ordered by name ascending."""
        matches = [
            branch
            for key, branch in self._state.branches.items()
            if key[0] == str(repository_id)
        ]
        matches.sort(key=lambda branch: branch.name)
        return tuple(matches)

    def delete(self, repository_id: RepositoryId, name: str) -> bool:
        """Delete a branch record."""
        return self._state.branches.pop((str(repository_id), name), None) is not None

    def replace_all(
        self, repository_id: RepositoryId, branches: Sequence[Branch]
    ) -> None:
        """Replace the recorded branch set atomically."""
        for key in [k for k in self._state.branches if k[0] == str(repository_id)]:
            del self._state.branches[key]
        for branch in branches:
            self._state.branches[(str(repository_id), branch.name)] = branch


class InMemoryFileUnitStore:
    """In-memory :class:`~ria.ports.repositories.FileUnitStore`."""

    def __init__(self, state: FakeState) -> None:
        self._state = state

    def add_many(self, units: Sequence[FileUnit]) -> int:
        """Insert file units in bulk, rejecting a batch spanning commits."""
        if not units:
            return 0
        first = units[0]
        for unit in units:
            if (
                unit.repository_id != first.repository_id
                or unit.commit_sha != first.commit_sha
            ):
                raise ValueError("batch must belong to a single repository and commit")
        for unit in units:
            self._state.file_units[
                (str(unit.repository_id), str(unit.commit_sha), unit.path)
            ] = unit
        return len(units)

    def get(
        self, repository_id: RepositoryId, sha: CommitSha, path: str
    ) -> Optional[FileUnit]:
        """Load one file unit."""
        return self._state.file_units.get((str(repository_id), str(sha), path))

    def list_by_commit(
        self,
        repository_id: RepositoryId,
        sha: CommitSha,
        *,
        limit: int = 1000,
        offset: int = 0,
    ) -> Sequence[FileUnit]:
        """List file units of a commit ordered by path ascending."""
        matches = [
            unit
            for key, unit in self._state.file_units.items()
            if key[0] == str(repository_id) and key[1] == str(sha)
        ]
        matches.sort(key=lambda unit: unit.path)
        return tuple(matches[offset : offset + limit])

    def content_hashes_by_commit(
        self, repository_id: RepositoryId, sha: CommitSha
    ) -> Dict[str, str]:
        """Map path to content hash for a commit."""
        return {
            unit.path: str(unit.content_hash)
            for unit in self.list_by_commit(repository_id, sha, limit=1_000_000)
        }

    def count_by_commit(self, repository_id: RepositoryId, sha: CommitSha) -> int:
        """Count file units of a commit."""
        return len(self.list_by_commit(repository_id, sha, limit=1_000_000))

    def delete_by_commit(self, repository_id: RepositoryId, sha: CommitSha) -> int:
        """Delete every file unit of a commit."""
        keys = [
            key
            for key in self._state.file_units
            if key[0] == str(repository_id) and key[1] == str(sha)
        ]
        for key in keys:
            del self._state.file_units[key]
        return len(keys)


class InMemoryJobStore:
    """In-memory :class:`~ria.ports.job_store.JobStore`.

    Reproduces the two behaviours the real adapter delegates to the database, so a
    unit test cannot pass where the SQLite adapter would behave differently:

    * ``enqueue`` is idempotent on ``(repository_id, idempotency_key)`` and returns
      the pre-existing job rather than raising or duplicating;
    * ``lease_next`` selects by priority, then availability, then creation order, so
      claim order is total and therefore deterministic.
    """

    def __init__(self, state: FakeState) -> None:
        self._state = state

    def enqueue(self, job: Job) -> Job:
        """Insert a job, or return the existing job with the same idempotency key."""
        existing = self.find_by_key(job.repository_id, job.idempotency_key)
        if existing is not None:
            return existing
        self._state.jobs[str(job.job_id)] = job
        return job

    def get(self, job_id: JobId) -> Optional[Job]:
        """Load a job by identifier."""
        return self._state.jobs.get(str(job_id))

    def find_by_key(
        self, repository_id: RepositoryId, idempotency_key: str
    ) -> Optional[Job]:
        """Load a job by its idempotency key."""
        for job in self._state.jobs.values():
            if (
                job.repository_id == repository_id
                and job.idempotency_key == idempotency_key
            ):
                return job
        return None

    def lease_next(
        self,
        *,
        owner: str,
        now: datetime,
        duration: timedelta,
        kinds: Optional[Sequence[JobKind]] = None,
        repository_id: Optional[RepositoryId] = None,
    ) -> Optional[Job]:
        """Claim the most urgent available job."""
        permitted = set(kinds) if kinds else None
        candidates = [
            job
            for job in self._state.jobs.values()
            if job.state is JobState.QUEUED
            and job.available_at <= now
            and (permitted is None or job.kind in permitted)
            and (repository_id is None or job.repository_id == repository_id)
        ]
        if not candidates:
            return None
        candidates.sort(
            key=lambda job: (
                job.priority,
                job.available_at,
                job.created_at,
                str(job.job_id),
            )
        )
        leased = candidates[0].leased(owner=owner, now=now, duration=duration)
        self._state.jobs[str(leased.job_id)] = leased
        return leased

    def save(self, job: Job) -> None:
        """Persist a job's new state."""
        key = str(job.job_id)
        if key not in self._state.jobs:
            raise JobNotFoundError("job is not recorded", {"job_id": key})
        self._state.jobs[key] = job

    def requeue_expired(self, *, now: datetime, limit: int = 100) -> Sequence[Job]:
        """Return jobs whose lease has lapsed to the queue."""
        if limit < 0:
            raise ValueError("limit must be non-negative")
        expired = [
            job for job in self._state.jobs.values() if job.lease_has_expired(now)
        ]
        expired.sort(key=lambda job: (job.leased_until, str(job.job_id)))
        reclaimed = []
        for job in expired[:limit]:
            updated = job.lease_expired(now=now)
            self._state.jobs[str(updated.job_id)] = updated
            reclaimed.append(updated)
        return tuple(reclaimed)

    def list_by_state(
        self,
        state: JobState,
        *,
        repository_id: Optional[RepositoryId] = None,
        limit: int = 100,
    ) -> Sequence[Job]:
        """List jobs in a given state, most urgent first."""
        if limit < 0:
            raise ValueError("limit must be non-negative")
        matches = [
            job
            for job in self._state.jobs.values()
            if job.state is state
            and (repository_id is None or job.repository_id == repository_id)
        ]
        matches.sort(key=lambda job: (job.priority, job.available_at, job.created_at))
        return tuple(matches[:limit])

    def count_by_state(
        self, repository_id: Optional[RepositoryId] = None
    ) -> Dict[str, int]:
        """Count jobs per state, omitting empty states."""
        counts: Dict[str, int] = {}
        for job in self._state.jobs.values():
            if repository_id is not None and job.repository_id != repository_id:
                continue
            counts[job.state.value] = counts.get(job.state.value, 0) + 1
        return counts

    def cancel_pending(self, repository_id: RepositoryId, *, now: datetime) -> int:
        """Cancel every job for a repository that has not yet completed."""
        cancellable = (JobState.QUEUED, JobState.LEASED, JobState.FAILED)
        cancelled = 0
        for key, job in list(self._state.jobs.items()):
            if job.repository_id != repository_id or job.state not in cancellable:
                continue
            self._state.jobs[key] = job.cancelled(now=now)
            cancelled += 1
        return cancelled

    def delete_by_repository(self, repository_id: RepositoryId) -> int:
        """Delete every job of a repository."""
        keys = [
            key
            for key, job in self._state.jobs.items()
            if job.repository_id == repository_id
        ]
        for key in keys:
            del self._state.jobs[key]
        return len(keys)


class InMemoryUnitOfWork:
    """In-memory :class:`~ria.ports.unit_of_work.UnitOfWork`.

    Copies the shared state on entry and publishes it on commit, so an uncommitted
    scope leaves no trace. Modelling rollback rather than writing straight through
    is what lets a test assert that a failed use case changed nothing.
    """

    def __init__(self, shared: FakeState) -> None:
        self._shared = shared
        self._working: Optional[FakeState] = None
        self._committed = False
        self._closed = False

    def __enter__(self) -> "InMemoryUnitOfWork":
        """Open the scope over a private copy of the shared state."""
        if self._closed:
            raise StorageError("unit of work has already been closed")
        self._working = self._shared.snapshot()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        """Close the scope, discarding the copy unless it was committed."""
        self._working = None
        self._closed = True

    def commit(self) -> None:
        """Publish this scope's writes to the shared state."""
        working = self._require_state()
        self._shared.adopt(working)
        self._committed = True

    def rollback(self) -> None:
        """Discard this scope's writes."""
        self._working = self._shared.snapshot()

    @property
    def repositories(self) -> InMemoryRepositoryStore:
        """Repository store bound to this scope."""
        return InMemoryRepositoryStore(self._require_state())

    @property
    def commits(self) -> InMemoryCommitStore:
        """Commit store bound to this scope."""
        return InMemoryCommitStore(self._require_state())

    @property
    def branches(self) -> InMemoryBranchStore:
        """Branch store bound to this scope."""
        return InMemoryBranchStore(self._require_state())

    @property
    def file_units(self) -> InMemoryFileUnitStore:
        """File unit store bound to this scope."""
        return InMemoryFileUnitStore(self._require_state())

    @property
    def jobs(self) -> InMemoryJobStore:
        """Job store bound to this scope."""
        return InMemoryJobStore(self._require_state())

    @property
    def was_committed(self) -> bool:
        """Whether this scope was committed."""
        return self._committed

    def _require_state(self) -> FakeState:
        """Return the working state, or raise if the scope is not open."""
        if self._working is None:
            raise StorageError("unit of work is not open; use it as a context manager")
        return self._working


class InMemoryUnitOfWorkFactory:
    """Creates :class:`InMemoryUnitOfWork` instances over one shared state.

    Satisfies :class:`~ria.ports.unit_of_work.UnitOfWorkFactory`.
    """

    def __init__(self, state: Optional[FakeState] = None) -> None:
        self.state = state or FakeState()
        #: Every scope created, so a test can assert commit behaviour.
        self.scopes: List[InMemoryUnitOfWork] = []

    def __call__(self) -> InMemoryUnitOfWork:
        """Create a new scope."""
        scope = InMemoryUnitOfWork(self.state)
        self.scopes.append(scope)
        return scope
