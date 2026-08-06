"""AST Generator service.

Generates deterministic :class:`~ria.domain.models.syntax_tree.SyntaxTree` objects from
source bytes via a :class:`~ria.ports.parser.ParserPort`.
"""

from __future__ import annotations

from typing import Optional

from ria.domain.models.syntax_tree import SyntaxTree
from ria.ports.parser import ParserPort

__all__ = ["AstGenerator"]


class AstGenerator:
    """Service that produces deterministic ASTs from raw source code.

    Attributes:
        parser: The underlying ParserPort adapter.
    """

    def __init__(self, parser: ParserPort) -> None:
        self._parser = parser

    def generate_ast(
        self,
        source_bytes: bytes,
        *,
        language: str,
        content_hash: str,
        timeout_seconds: Optional[float] = None,
    ) -> SyntaxTree:
        """Generate a deterministic SyntaxTree.

        The same source bytes, language, and content_hash will always yield an identical
        SyntaxTree with identical structural digest.

        Args:
            source_bytes: Raw source code bytes.
            language: Canonical language name.
            content_hash: Canonical content hash of the bytes.
            timeout_seconds: Optional parse timeout.

        Returns:
            The parsed SyntaxTree.
        """
        return self._parser.parse_bytes(
            source_bytes,
            language=language,
            content_hash=content_hash,
            timeout_seconds=timeout_seconds,
        )
