"""Filesystem Port abstraction."""

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class FilesystemPort(Protocol):
    """Protocol for abstracting filesystem reading, walking, and metadata inspection.

    Preconditions: Paths must be valid OS paths.
    Postconditions: Returns file content bytes and file tree sequences.
    """

    def walk_directory(
        self, root: Path, ignore_patterns: Sequence[str] = ()
    ) -> Sequence[Path]:
        """Walk directory tree from root, skipping paths matching ignore_patterns."""
        ...

    def read_bytes(self, path: Path) -> bytes:
        """Read raw binary contents of file at path."""
        ...

    def exists(self, path: Path) -> bool:
        """Check if file or directory exists at path."""
        ...

    def get_size(self, path: Path) -> int:
        """Return size in bytes of file at path."""
        ...
