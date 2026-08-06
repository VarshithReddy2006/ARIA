"""Repository Scanner Service."""

from collections.abc import Sequence
from pathlib import Path

from ria.application.index.discovery import FileDiscovery
from ria.application.index.language import LanguageDetection
from ria.domain.index.units import FileUnit
from ria.domain.index.value_objects import FilePath
from ria.ports.index.filesystem import FilesystemPort
from ria.ports.index.hashing import HashingPort
from ria.ports.index.scanner import ScannerPort


class RepositoryScanner(ScannerPort):
    """Scanner coordinating file discovery, language detection, and content hashing to yield FileUnits."""

    def __init__(
        self,
        discovery: FileDiscovery,
        language_detection: LanguageDetection,
        filesystem: FilesystemPort,
        hashing: HashingPort,
    ) -> None:
        self._discovery = discovery
        self._lang_detect = language_detection
        self._fs = filesystem
        self._hashing = hashing

    def scan_repository(self, workspace_path: Path) -> Sequence[FileUnit]:
        """Perform full directory scan of repository workspace and return FileUnits."""
        rel_paths = self._discovery.discover_files(workspace_path)
        file_units: list[FileUnit] = []

        for rel_fp in rel_paths:
            abs_p = workspace_path / rel_fp.relative_path
            lang = self._lang_detect.detect_language(abs_p, rel_fp)
            size = self._fs.get_size(abs_p)
            content_hash = self._hashing.hash_file(abs_p, self._fs)

            unit = FileUnit(
                path=rel_fp,
                language=lang,
                content_hash=content_hash,
                size_bytes=size,
            )
            file_units.append(unit)

        return tuple(file_units)

    def scan_incremental(
        self,
        workspace_path: Path,
        changed_files: Sequence[FilePath],
    ) -> Sequence[FileUnit]:
        """Perform targeted scan of specified changed files in repository workspace."""
        file_units: list[FileUnit] = []

        for rel_fp in changed_files:
            abs_p = workspace_path / rel_fp.relative_path
            if not self._fs.exists(abs_p):
                continue
            if self._discovery.is_binary_or_oversized(abs_p):
                continue

            lang = self._lang_detect.detect_language(abs_p, rel_fp)
            size = self._fs.get_size(abs_p)
            content_hash = self._hashing.hash_file(abs_p, self._fs)

            unit = FileUnit(
                path=rel_fp,
                language=lang,
                content_hash=content_hash,
                size_bytes=size,
            )
            file_units.append(unit)

        return tuple(file_units)
