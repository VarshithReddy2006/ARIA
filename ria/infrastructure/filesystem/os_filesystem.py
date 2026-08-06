"""OS Filesystem Adapter implementing FilesystemPort."""

import fnmatch
from collections.abc import Sequence
from pathlib import Path

from ria.infrastructure.exceptions import FilesystemError
from ria.ports.index.filesystem import FilesystemPort


class OSFilesystemAdapter(FilesystemPort):
    """Real OS filesystem adapter with path validation and pattern-based ignore filtering."""

    DEFAULT_IGNORE_PATTERNS: tuple[str, ...] = (
        "*.git*",
        "*node_modules*",
        "*__pycache__*",
        "*.venv*",
        "*.pytest_cache*",
        "*.mypy_cache*",
        "*.DS_Store*",
    )

    def _should_ignore(self, path: Path, ignore_patterns: Sequence[str]) -> bool:
        combined_patterns = list(self.DEFAULT_IGNORE_PATTERNS) + list(ignore_patterns)
        path_str = str(path)
        name = path.name
        for pattern in combined_patterns:
            if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(path_str, pattern):
                return True
        return False

    def walk_directory(self, root: Path, ignore_patterns: Sequence[str] = ()) -> Sequence[Path]:
        """Walk directory tree from root, skipping paths matching ignore_patterns."""
        if not root.exists():
            raise FilesystemError(f"Root directory '{root}' does not exist.")
        if not root.is_dir():
            raise FilesystemError(f"Root path '{root}' is not a directory.")

        discovered: list[Path] = []
        try:
            for item in root.rglob("*"):
                if self._should_ignore(item, ignore_patterns):
                    continue
                if item.is_file():
                    discovered.append(item)
            return tuple(sorted(discovered))
        except OSError as err:
            raise FilesystemError(f"Failed to walk directory '{root}': {err}") from err

    def read_bytes(self, path: Path) -> bytes:
        """Read raw binary contents of file at path."""
        if not path.exists():
            raise FilesystemError(f"File '{path}' does not exist.")
        if not path.is_file():
            raise FilesystemError(f"Path '{path}' is not a file.")
        try:
            return path.read_bytes()
        except OSError as err:
            raise FilesystemError(f"Failed to read file '{path}': {err}") from err

    def exists(self, path: Path) -> bool:
        """Check if file or directory exists at path."""
        try:
            return path.exists()
        except OSError as err:
            raise FilesystemError(f"Error checking existence of path '{path}': {err}") from err

    def get_size(self, path: Path) -> int:
        """Return size in bytes of file at path."""
        if not path.exists():
            raise FilesystemError(f"File '{path}' does not exist.")
        try:
            return path.stat().st_size
        except OSError as err:
            raise FilesystemError(f"Failed to get size for file '{path}': {err}") from err
