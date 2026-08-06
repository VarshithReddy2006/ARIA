"""Symbol identity value object.

Implements immutable, deterministic identity for symbols across files and commits.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ria.domain.models.span import SourceSpan

__all__ = ["SymbolId"]


@dataclass(frozen=True)
class SymbolId:
    """Immutable identity of a semantic Symbol.

    Attributes:
        value: String representation of the symbol identity.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("symbol_id value must be non-empty")

    @classmethod
    def for_symbol(
        cls,
        language: str,
        file_path: str,
        qualified_name: str,
        span: SourceSpan,
    ) -> SymbolId:
        """Construct a deterministic SymbolId from symbol attributes.

        Args:
            language: Canonical language name.
            file_path: Normalised repository-relative path.
            qualified_name: Fully qualified name within the file/module.
            span: SourceSpan where the symbol is declared.

        Returns:
            A deterministic SymbolId instance.
        """
        raw_key = f"{language}:{file_path}:{qualified_name}:{span.start.line}:{span.start.column}-{span.end.line}:{span.end.column}"
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]
        return cls(value=f"sym:{language}:{file_path}:{qualified_name}:{digest}")

    def __str__(self) -> str:
        return self.value
