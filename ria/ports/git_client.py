"""Git client port.

SDD section 3 (L1) makes git the system of record: "we never own the truth". This
port is the only way the system reads from it.

Raw data transfer objects
-------------------------
The port returns :class:`RawCommit` and :class:`RawBranch` rather than domain
entities. Git cannot know a :class:`~ria.domain.identity.RepositoryId`, so an
adapter that returned :class:`~ria.domain.models.commit.Commit` would have to
invent one or accept it as a parameter — either way pushing domain knowledge into
infrastructure and inverting the dependency rule of SDD section 2.3. Mapping raw
observations to entities is the application layer's responsibility.

Scope
-----
Milestone 1 declared the read-only operations against a local git directory: ref
resolution, commit metadata, branch enumeration and tree listing.

Milestone 2 adds acquisition and history walking: :meth:`GitClient.clone_mirror`,
:meth:`GitClient.fetch`, :meth:`GitClient.list_commits` and
:meth:`GitClient.open_blob`. Acquisition is the only part of this interface that
writes, and it writes only to our own mirror directory — never to the upstream
repository, which remains the system of record.

:meth:`GitClient.open_blob` exists so that a blob larger than the configured memory
limit can still be content-addressed. Without a streaming read the only options for
an oversized file are to buffer it whole, defeating the limit, or to record it with
no content hash, which the entity model forbids.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import (
    IO,
    ContextManager,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    runtime_checkable,
)

__all__ = [
    "GitVersion",
    "RawSignature",
    "RawCommit",
    "RawCommitSummary",
    "RawBranch",
    "RawTreeEntry",
    "GitClient",
]


@dataclass(frozen=True)
class GitVersion:
    """Version of the git executable in use.

    Recorded in provenance because git's behaviour for rename detection and tree
    listing has changed across versions, and a reproducibility investigation
    needs to know which version produced an observation.

    Attributes:
        raw: Unparsed output of ``git --version``.
        major: Major version component.
        minor: Minor version component.
        patch: Patch version component.
    """

    raw: str
    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class RawSignature:
    """An authorship signature exactly as git reports it.

    Attributes:
        name: Display name, possibly empty.
        email: Email address, possibly empty.
        timestamp: Timezone-aware instant recorded in the signature.
    """

    name: str
    email: str
    timestamp: datetime


@dataclass(frozen=True)
class RawCommit:
    """Commit metadata exactly as git reports it.

    Attributes:
        sha: Full object name.
        parent_shas: Parent object names in git order.
        tree_sha: Tree object name.
        author: Authorship signature.
        committer: Committer signature.
        message: Full commit message including body.
    """

    sha: str
    parent_shas: Tuple[str, ...]
    tree_sha: str
    author: RawSignature
    committer: RawSignature
    message: str


@dataclass(frozen=True)
class RawCommitSummary:
    """Minimal commit metadata, for walking history cheaply.

    Distinct from :class:`RawCommit` because commit discovery walks thousands of
    commits and needs only enough to apply a snapshot cadence policy. Reading full
    metadata for each would cost one subprocess invocation per commit; this shape is
    produced for the whole range in a single invocation.

    Attributes:
        sha: Full object name.
        parent_shas: Parent object names in git order.
        committed_at: Committer timestamp, in UTC.
    """

    sha: str
    parent_shas: Tuple[str, ...]
    committed_at: datetime

    @property
    def is_merge(self) -> bool:
        """Whether the commit has more than one parent."""
        return len(self.parent_shas) > 1


@dataclass(frozen=True)
class RawBranch:
    """Branch metadata exactly as git reports it.

    Attributes:
        name: Branch name without the ``refs/heads/`` prefix.
        head_sha: Object name the branch points at.
        is_default: Whether git reports this as the repository head.
        last_commit_at: Committer timestamp of the head commit.
    """

    name: str
    head_sha: str
    is_default: bool = False
    last_commit_at: Optional[datetime] = None


@dataclass(frozen=True)
class RawTreeEntry:
    """One blob in a commit's tree, as reported by git.

    Only blobs are returned; trees and submodule links are excluded by the
    adapter, because a submodule is ingested as a separate repository per SDD
    section 3 (L1 failure modes) and a tree carries no content.

    Attributes:
        path: Repository-relative path as git reports it, using forward slashes.
        blob_sha: Blob object name.
        size_bytes: Blob size in bytes.
        mode: Git file mode, for example ``100644``. ``120000`` denotes a symlink,
            which the ingestion layer must not follow.
    """

    path: str
    blob_sha: str
    size_bytes: int
    mode: str

    @property
    def is_symlink(self) -> bool:
        """Whether the entry is a symbolic link rather than a regular file."""
        return self.mode == "120000"

    @property
    def is_executable(self) -> bool:
        """Whether the entry has the executable bit set."""
        return self.mode == "100755"


@runtime_checkable
class GitClient(Protocol):
    """Read-only access to a local git directory.

    Every method takes the path of a git directory — a working clone or a bare
    mirror — because one process serves many repositories and holding per-instance
    repository state would prevent that.

    Implementations must never write to the repository, must never prompt for
    credentials, and must impose a timeout on every invocation so that a hung
    subprocess cannot stall a worker indefinitely.
    """

    def version(self) -> GitVersion:
        """Return the version of the git executable.

        Raises:
            GitUnavailableError: If git is absent or not runnable.
        """
        ...

    def resolve_ref(self, repository_path: Path, ref: str) -> str:
        """Resolve a ref expression to a full object name.

        Abbreviated SHAs are expanded, so the caller never receives an ambiguous
        identity.

        Args:
            repository_path: Path of the git directory.
            ref: Branch name, tag, full or abbreviated SHA, or any expression git
                accepts.

        Returns:
            The full 40 or 64 character object name.

        Raises:
            RefNotFoundError: If the ref does not resolve to a commit.
            GitCommandError: If the git invocation fails for another reason.
        """
        ...

    def read_commit(self, repository_path: Path, sha: str) -> RawCommit:
        """Read the metadata of one commit.

        Args:
            repository_path: Path of the git directory.
            sha: Full object name of the commit.

        Returns:
            The commit's metadata.

        Raises:
            RefNotFoundError: If the object does not exist or is not a commit.
            GitCommandError: If the git invocation fails.
        """
        ...

    def list_branches(self, repository_path: Path) -> Sequence[RawBranch]:
        """Enumerate local branches.

        Args:
            repository_path: Path of the git directory.

        Returns:
            Every local branch, with the default branch flagged. Order is
            unspecified; callers that need determinism must sort.

        Raises:
            GitCommandError: If the git invocation fails.
        """
        ...

    def detect_default_branch(self, repository_path: Path) -> str:
        """Determine the repository's default branch name.

        Args:
            repository_path: Path of the git directory.

        Returns:
            The default branch name without a ``refs/heads/`` prefix.

        Raises:
            RefNotFoundError: If no default branch can be determined, which
                happens for a repository with no commits.
        """
        ...

    def list_tree(self, repository_path: Path, sha: str) -> Sequence[RawTreeEntry]:
        """List every blob reachable from a commit's tree.

        Args:
            repository_path: Path of the git directory.
            sha: Full object name of the commit.

        Returns:
            One entry per blob, recursively, excluding trees and submodules.

        Raises:
            RefNotFoundError: If the commit does not exist.
            GitCommandError: If the git invocation fails.
        """
        ...

    def read_blob(self, repository_path: Path, blob_sha: str) -> bytes:
        """Read the raw content of a blob.

        Args:
            repository_path: Path of the git directory.
            blob_sha: Blob object name.

        Returns:
            The blob's bytes.

        Raises:
            GitCommandError: If the object does not exist or cannot be read.
        """
        ...

    def open_blob(
        self, repository_path: Path, blob_sha: str
    ) -> ContextManager[IO[bytes]]:
        """Open a blob as a managed binary stream.

        The returned object is a context manager so that the underlying process is
        always reaped, including when the caller abandons the stream part-way.

        Used to content-address a blob too large to hold in memory: the caller reads
        it in fixed-size chunks and digests as it goes, giving ``O(1)`` memory.

        Args:
            repository_path: Path of the git directory.
            blob_sha: Blob object name.

        Returns:
            A context manager yielding a readable binary stream.

        Raises:
            GitCommandError: If the object does not exist or cannot be read.
        """
        ...

    def clone_mirror(self, origin_url: str, destination: Path) -> None:
        """Create a bare mirror of a repository.

        A mirror rather than a working clone: every read this system performs is an
        object read, so a working tree would double the disk cost and add nothing. A
        mirror also copies every ref, which branch discovery depends on.

        Must be atomic from the caller's perspective: a failed clone must not leave a
        partial directory that a later call would mistake for a usable mirror.

        Args:
            origin_url: Upstream URL or local path.
            destination: Directory to create. Must not already exist.

        Raises:
            GitCommandError: If the clone fails.
        """
        ...

    def fetch(self, repository_path: Path, *, prune: bool = True) -> None:
        """Update an existing mirror from its origin.

        Args:
            repository_path: Path of the mirror.
            prune: Whether to delete local refs whose upstream counterpart is gone.
                Enabled by default, because a mirror that retains deleted branches
                would report a branch set that no longer exists.

        Raises:
            GitCommandError: If the fetch fails.
        """
        ...

    def list_commits(
        self,
        repository_path: Path,
        ref: str,
        *,
        limit: int,
        since: Optional[datetime] = None,
    ) -> Sequence[RawCommitSummary]:
        """Walk history from a ref, newest first.

        Args:
            repository_path: Path of the git directory.
            ref: Starting ref expression.
            limit: Maximum number of commits. Required rather than optional, because
                an unbounded walk over a large repository is never what a caller
                wants and would be discovered only under load.
            since: Only include commits at or after this instant.

        Returns:
            Commit summaries, newest first.

        Raises:
            ValueError: If the limit is not positive.
            RefNotFoundError: If the ref does not resolve.
            GitCommandError: If the invocation fails.
        """
        ...

    def count_lines(self, data: bytes) -> Optional[int]:
        """Count the lines in file content, or return ``None`` if it is binary.

        Placed on this port because the definition of "binary" that matters is
        git's own: a file git treats as binary must not be parsed, chunked or
        embedded, and reimplementing that judgement elsewhere would produce a
        second, divergent definition.

        Args:
            data: File content.

        Returns:
            Line count for text content, or ``None`` for binary content.
        """
        ...
