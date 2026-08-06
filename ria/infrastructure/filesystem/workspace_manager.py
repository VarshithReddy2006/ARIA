"""Workspace Manager Adapter implementing WorkspacePort."""

import shutil
from pathlib import Path

from ria.domain.sync.value_objects import RepositoryIdentity
from ria.infrastructure.exceptions import WorkspaceError
from ria.ports.sync.workspace import WorkspacePort


class WorkspaceManager(WorkspacePort):
    """Local filesystem workspace manager allocating isolated workspace directories."""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir.resolve()
        try:
            self._base_dir.mkdir(parents=True, exist_ok=True)
        except OSError as err:
            raise WorkspaceError(f"Failed to initialize base workspace dir '{self._base_dir}': {err}") from err

    def _validate_workspace_path(self, path: Path) -> Path:
        """Ensure path does not escape base workspace root."""
        resolved = path.resolve()
        try:
            resolved.relative_to(self._base_dir)
        except ValueError as err:
            raise WorkspaceError(f"Path traversal security violation: '{resolved}' escapes base directory '{self._base_dir}'.") from err
        return resolved

    def get_workspace_path(self, repo_id: RepositoryIdentity) -> Path:
        """Return target filesystem path for repository workspace."""
        repo_dir = self._base_dir / f"repo_{repo_id.repo_id.value}"
        return self._validate_workspace_path(repo_dir)

    def create_workspace(self, repo_id: RepositoryIdentity) -> Path:
        """Ensure working directory exists on disk and return path."""
        target = self.get_workspace_path(repo_id)
        try:
            target.mkdir(parents=True, exist_ok=True)
            return target
        except OSError as err:
            raise WorkspaceError(f"Failed to create workspace '{target}': {err}") from err

    def delete_workspace(self, repo_id: RepositoryIdentity) -> bool:
        """Remove repository working directory and content from disk."""
        target = self.get_workspace_path(repo_id)
        if not target.exists():
            return False
        try:
            shutil.rmtree(target)
            return True
        except OSError as err:
            raise WorkspaceError(f"Failed to delete workspace '{target}': {err}") from err

    def create_ephemeral_workspace(self, repo_id: RepositoryIdentity, suffix: str) -> Path:
        """Create temporary isolated workspace directory for branch/session comparison."""
        ephemeral_dir = self._base_dir / f"repo_{repo_id.repo_id.value}_ephemeral_{suffix}"
        target = self._validate_workspace_path(ephemeral_dir)
        try:
            target.mkdir(parents=True, exist_ok=True)
            return target
        except OSError as err:
            raise WorkspaceError(f"Failed to create ephemeral workspace '{target}': {err}") from err
