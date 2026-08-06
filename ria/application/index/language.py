"""Language Detection Service."""

from pathlib import Path

from ria.domain.index.value_objects import FilePath, Language
from ria.ports.index.filesystem import FilesystemPort


class LanguageDetection:
    """Detects programming language from file extension or shebang header."""

    def __init__(self, filesystem: FilesystemPort) -> None:
        self._fs = filesystem

    def detect_language(self, abs_path: Path, file_path: FilePath) -> Language:
        """Determine language for a file by extension first, then shebang fallback."""
        ext_lang = Language.from_extension(file_path.extension)
        if ext_lang != Language.UNKNOWN:
            return ext_lang

        # Shebang fallback for extensionless files
        try:
            content = self._fs.read_bytes(abs_path)
            first_line = (
                content.split(b"\n", 1)[0].decode("utf-8", errors="ignore").strip()
            )
            if first_line.startswith("#!"):
                if "python" in first_line:
                    return Language.PYTHON
                if "node" in first_line or "deno" in first_line:
                    return Language.JAVASCRIPT
        except Exception:
            pass

        return Language.UNKNOWN
