"""Scanner Port abstraction."""

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from ria.domain.index.units import FileUnit
from ria.domain.index.value_objects import FilePath


@runtime_checkable
class ScannerPort(Protocol):
    """Protocol for discovering, filtering, and hashing files in a repository workspace.

    Preconditions: Workspace path must exist on disk.
    Postconditions: Returns sequence of discovered immutable FileUnit value objects.
    """

    def scan_repository(self, workspace_path: Path) -> Sequence[FileUnit]:
        """Perform full directory scan of repository workspace and return FileUnits."""
        ...

    def scan_incremental(
        self,
        workspace_path: Path,
        changed_files: Sequence[FilePath],
    ) -> Sequence[FileUnit]:
        """Perform targeted scan of specified changed files in repository workspace."""
        ...
