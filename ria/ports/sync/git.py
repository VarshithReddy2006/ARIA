"""Git Client Port abstraction."""

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from ria.domain.index.value_objects import FilePath
from ria.domain.sync.value_objects import CommitReference, RepositoryMetadata


@runtime_checkable
class GitClientPort(Protocol):
    """Protocol for abstracting Git VCS client operations.

    Preconditions: Path arguments must exist or be writable. Remote URLs must be valid Git URIs.
    Postconditions: Clones, fetches, checkouts repositories and returns immutable domain ValueObjects.
    Raises: SyncDomainException on command failure or invalid refs.
    """

    def clone(self, remote_url: str, destination_dir: Path) -> CommitReference:
        """Clone remote git repository to local path and return head commit reference."""
        ...

    def fetch(self, repo_dir: Path) -> None:
        """Fetch remote refs and objects for existing cloned repository."""
        ...

    def checkout(self, repo_dir: Path, branch_or_sha: str) -> CommitReference:
        """Checkout specified branch name or commit SHA and return checked-out commit reference."""
        ...

    def get_current_commit(self, repo_dir: Path) -> CommitReference:
        """Query current HEAD commit SHA and timestamp."""
        ...

    def detect_changed_files(self, repo_dir: Path, base_sha: str, head_sha: str) -> Sequence[FilePath]:
        """Compute list of relative FilePaths modified between base_sha and head_sha."""
        ...

    def get_metadata(self, repo_dir: Path, default_branch: str) -> RepositoryMetadata:
        """Inspect repository and return file count, total bytes, and default branch metadata."""
        ...
