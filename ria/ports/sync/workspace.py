"""Workspace Port abstraction."""

from pathlib import Path
from typing import Protocol, runtime_checkable

from ria.domain.sync.value_objects import RepositoryIdentity


@runtime_checkable
class WorkspacePort(Protocol):
    """Protocol for managing local filesystem working directories for repositories.

    Preconditions: RepositoryIdentity must be non-null.
    Postconditions: Returns valid local Path objects for repository operations.
    """

    def get_workspace_path(self, repo_id: RepositoryIdentity) -> Path:
        """Return target filesystem path for repository workspace."""
        ...

    def create_workspace(self, repo_id: RepositoryIdentity) -> Path:
        """Ensure working directory exists on disk and return path."""
        ...

    def delete_workspace(self, repo_id: RepositoryIdentity) -> bool:
        """Remove repository working directory and content from disk."""
        ...

    def create_ephemeral_workspace(
        self, repo_id: RepositoryIdentity, suffix: str
    ) -> Path:
        """Create temporary isolated workspace directory for branch/session comparison."""
        ...
