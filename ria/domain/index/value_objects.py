"""Value Objects for C1 Index Core Domain."""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Tuple

from ria.domain.common.base import ValueObject


class Language(Enum):
    """Supported programming languages in Foundation Iteration 1."""

    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    UNKNOWN = "unknown"

    @classmethod
    def from_extension(cls, ext: str) -> "Language":
        normalized = ext.lower().lstrip(".")
        mapping = {
            "py": cls.PYTHON,
            "ts": cls.TYPESCRIPT,
            "tsx": cls.TYPESCRIPT,
            "js": cls.JAVASCRIPT,
            "jsx": cls.JAVASCRIPT,
            "mjs": cls.JAVASCRIPT,
            "cjs": cls.JAVASCRIPT,
        }
        return mapping.get(normalized, cls.UNKNOWN)


@dataclass(frozen=True, slots=True)
class FilePath(ValueObject):
    """Immutable representation of a normalized relative file path."""

    relative_path: str

    def _validate_invariants(self) -> None:
        if not self.relative_path or not self.relative_path.strip():
            raise ValueError("FilePath cannot be empty.")
        if "\\" in self.relative_path:
            raise ValueError("FilePath must use POSIX forward slash '/' separators.")
        if self.relative_path.startswith("/"):
            raise ValueError("FilePath must be relative, not absolute.")

    @property
    def extension(self) -> str:
        parts = self.relative_path.rsplit(".", 1)
        return f".{parts[1]}" if len(parts) > 1 else ""


@dataclass(frozen=True, slots=True)
class ContentHash(ValueObject):
    """Immutable SHA-256 hash of file content."""

    sha256_hex: str

    def _validate_invariants(self) -> None:
        if not re.match(r"^[0-9a-fA-F]{64}$", self.sha256_hex):
            raise ValueError(f"ContentHash must be a 64-character hex string, got '{self.sha256_hex}'.")


@dataclass(frozen=True, slots=True)
class Location(ValueObject):
    """Immutable 1-indexed line and 0-indexed column code location range."""

    start_line: int
    start_col: int
    end_line: int
    end_col: int

    def _validate_invariants(self) -> None:
        if self.start_line < 1 or self.end_line < 1:
            raise ValueError("Line numbers must be 1-indexed (>= 1).")
        if self.start_col < 0 or self.end_col < 0:
            raise ValueError("Column numbers must be 0-indexed (>= 0).")
        if (self.start_line, self.start_col) > (self.end_line, self.end_col):
            raise ValueError("Start location must be before or equal to end location.")


@dataclass(frozen=True, slots=True)
class ASTNode(ValueObject):
    """Immutable, serializable tree-sitter AST Node."""

    type: str
    start_line: int
    start_col: int
    end_line: int
    end_col: int
    attributes: Tuple[Tuple[str, str], ...] = field(default_factory=tuple)
    children: Tuple["ASTNode", ...] = field(default_factory=tuple)

    def _validate_invariants(self) -> None:
        if not self.type:
            raise ValueError("ASTNode type cannot be empty.")
        if self.start_line < 1 or self.end_line < 1:
            raise ValueError("Line numbers must be >= 1.")
