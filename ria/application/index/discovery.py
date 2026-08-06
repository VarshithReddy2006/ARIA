"""File Discovery Service."""

from collections.abc import Sequence
from pathlib import Path

from ria.domain.index.value_objects import FilePath
from ria.ports.index.filesystem import FilesystemPort


class FileDiscovery:
    """Discovers indexable source files in a repository workspace, filtering ignored, binary, and oversized paths."""

    BINARY_EXTENSIONS: tuple[str, ...] = (
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".bin",
        ".pyc",
        ".pyo",
        ".pyd",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".ico",
        ".pdf",
        ".zip",
        ".tar",
        ".gz",
    )

    def __init__(
        self, filesystem: FilesystemPort, max_file_size_bytes: int = 2 * 1024 * 1024
    ) -> None:
        self._fs = filesystem
        self._max_size = max_file_size_bytes

    def is_binary_or_oversized(self, abs_path: Path) -> bool:
        """Check if file should be skipped due to binary extension or exceeding size limit."""
        ext = abs_path.suffix.lower()
        if ext in self.BINARY_EXTENSIONS:
            return True
        try:
            return self._fs.get_size(abs_path) > self._max_size
        except Exception:
            return True

    def discover_files(
        self, workspace_path: Path, ignore_patterns: Sequence[str] = ()
    ) -> Sequence[FilePath]:
        """Discover indexable relative FilePaths under workspace_path."""
        abs_paths = self._fs.walk_directory(workspace_path, ignore_patterns)
        discovered: list[FilePath] = []

        for abs_p in abs_paths:
            if self.is_binary_or_oversized(abs_p):
                continue
            try:
                rel = abs_p.relative_to(workspace_path)
                posix_rel = str(rel).replace("\\", "/")
                discovered.append(FilePath(relative_path=posix_rel))
            except ValueError:
                continue

        return tuple(discovered)
