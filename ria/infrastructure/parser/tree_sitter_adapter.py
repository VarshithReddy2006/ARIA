"""Tree-sitter parser adapter implementation.

Implements the :class:`~ria.ports.parser.ParserPort` interface using tree-sitter grammars.
Converts tree-sitter C/Python node structures into domain value objects
(:class:`~ria.domain.models.syntax_tree.SyntaxNode` and
:class:`~ria.domain.models.syntax_tree.SyntaxTree`).

Clean Architecture Invariant
----------------------------
Tree-sitter imports are isolated entirely inside this module (and language grammar loader
helpers). No domain model or application service ever receives or imports a tree-sitter
object directly.
"""

from __future__ import annotations

import threading
from typing import Callable, Dict, List, Optional, Tuple

from ria.domain.errors import InfrastructureError
from ria.domain.models.parser_identity import ComponentVersion
from ria.domain.models.span import SourcePosition, SourceSpan
from ria.domain.models.syntax_tree import SyntaxNode, SyntaxTree
from ria.observability.metrics import NullMetricsSink
from ria.ports.metrics import MetricsSink
from ria.ports.parser import ParserPort

__all__ = ["TreeSitterAdapter", "GrammarLoader"]

#: Grammar loader type signature: returns a raw tree-sitter language pointer / C-object
GrammarLoader = Callable[[], object]


def _load_python_grammar() -> object:
    import tree_sitter_python

    return tree_sitter_python.language()


def _load_javascript_grammar() -> object:
    import tree_sitter_javascript

    return tree_sitter_javascript.language()


def _load_typescript_grammar() -> object:
    import tree_sitter_typescript

    return tree_sitter_typescript.language_typescript()


def _load_tsx_grammar() -> object:
    import tree_sitter_typescript

    return tree_sitter_typescript.language_tsx()


#: Built-in language grammar registry mapping canonical language name to loader and version
DEFAULT_GRAMMAR_LOADERS: Dict[str, Tuple[GrammarLoader, str]] = {
    "python": (_load_python_grammar, "0.21.0"),
    "javascript": (_load_javascript_grammar, "0.21.0"),
    "typescript": (_load_typescript_grammar, "0.21.0"),
    "tsx": (_load_tsx_grammar, "0.21.0"),
}


class TreeSitterAdapter(ParserPort):
    """Adapter wrapping tree-sitter parsing engine behind ParserPort.

    Features:
    - Thread-local parser caching (tree-sitter Parser is not thread-safe across concurrent calls).
    - Conversions from tree-sitter C nodes into immutable domain SyntaxNode trees.
    - Captures missing and error nodes accurately.
    - Zero tree-sitter leaks outside infrastructure.
    """

    def __init__(
        self,
        loaders: Optional[Dict[str, Tuple[GrammarLoader, str]]] = None,
        metrics: Optional[MetricsSink] = None,
    ) -> None:
        self._loaders = loaders if loaders is not None else DEFAULT_GRAMMAR_LOADERS
        self._metrics = metrics or NullMetricsSink()
        self._local = threading.local()

    def parse_bytes(
        self,
        source_bytes: bytes,
        *,
        language: str,
        content_hash: str,
        timeout_seconds: Optional[float] = None,
    ) -> SyntaxTree:
        """Parse source bytes into a domain SyntaxTree.

        Args:
            source_bytes: Raw file content bytes.
            language: Canonical language name.
            content_hash: Content hash string.
            timeout_seconds: Optional parse timeout.

        Returns:
            The parsed SyntaxTree.

        Raises:
            ValueError: If the language is unsupported or arguments are invalid.
            InfrastructureError: If tree-sitter fails catastrophically.
        """
        if not language:
            raise ValueError("language must be non-empty")
        if not content_hash:
            raise ValueError("content_hash must be non-empty")
        if language not in self._loaders:
            raise ValueError(
                f"unsupported language for tree-sitter parsing: {language!r}"
            )

        parser = self._get_parser(language)

        try:
            ts_tree = parser.parse(source_bytes)
        except Exception as exc:
            raise InfrastructureError(
                f"tree-sitter parse failed for language {language!r}: {exc}",
                context={"language": language, "content_hash": content_hash},
            ) from exc

        root_ts = ts_tree.root_node
        domain_root = self._convert_node(root_ts, source_bytes_len=len(source_bytes))

        return SyntaxTree(
            language=language,
            root=domain_root,
            content_hash=content_hash,
            source_bytes=len(source_bytes),
            truncated=False,
        )

    def parser_version(self, language: str) -> ComponentVersion:
        """Return ComponentVersion for the given language parser."""
        if language not in self._loaders:
            raise ValueError(
                f"unsupported language for tree-sitter parsing: {language!r}"
            )
        _, version_str = self._loaders[language]
        return ComponentVersion(name=f"tree-sitter-{language}", version=version_str)

    # -- Internal Parser Lifecycle -----------------------------------------

    def _get_parser(self, language: str) -> object:
        """Get or initialize thread-local tree-sitter Parser instance."""
        if not hasattr(self._local, "parsers"):
            self._local.parsers = {}

        if language in self._local.parsers:
            return self._local.parsers[language]

        from tree_sitter import Language, Parser

        loader, _ = self._loaders[language]
        lang_ptr = loader()
        ts_lang = Language(lang_ptr, language)

        parser = Parser()
        parser.set_language(ts_lang)
        self._local.parsers[language] = parser
        return parser

    # -- Node Conversion --------------------------------------------------

    def _convert_node(self, ts_node: object, source_bytes_len: int) -> SyntaxNode:
        """Iteratively / recursively convert a tree-sitter Node to a SyntaxNode domain object."""
        # Extract span
        start_byte, end_byte = ts_node.start_byte, ts_node.end_byte
        start_line, start_col = ts_node.start_point[0], ts_node.start_point[1]
        end_line, end_col = ts_node.end_point[0], ts_node.end_point[1]

        # Clamp offsets to source_bytes_len if tree-sitter reports out of range
        if end_byte > source_bytes_len:
            end_byte = source_bytes_len
        if start_byte > end_byte:
            start_byte = end_byte

        span = SourceSpan(
            start=SourcePosition(byte=start_byte, line=start_line, column=start_col),
            end=SourcePosition(byte=end_byte, line=end_line, column=end_col),
        )

        kind = ts_node.type
        is_named = ts_node.is_named
        is_error = kind == "ERROR" or ts_node.has_error
        is_missing = ts_node.is_missing

        # If node is missing, ensure zero-width span as domain invariant requires
        if is_missing and not span.is_empty:
            span = SourceSpan.empty_at(span.start)

        # Convert children
        children_list: List[SyntaxNode] = []
        for child_ts in ts_node.children:
            field_name = (
                ts_node.field_name_for_child(child_ts.id)
                if hasattr(ts_node, "field_name_for_child")
                else None
            )
            child_domain = self._convert_node_with_field(
                child_ts, field_name, source_bytes_len
            )
            children_list.append(child_domain)

        return SyntaxNode(
            kind=kind,
            span=span,
            children=tuple(children_list),
            field_name=None,
            is_named=is_named,
            is_error=is_error,
            is_missing=is_missing,
        )

    def _convert_node_with_field(
        self, ts_node: object, field_name: Optional[str], source_bytes_len: int
    ) -> SyntaxNode:
        """Convert child node carrying parent's field_name."""
        start_byte, end_byte = ts_node.start_byte, ts_node.end_byte
        start_line, start_col = ts_node.start_point[0], ts_node.start_point[1]
        end_line, end_col = ts_node.end_point[0], ts_node.end_point[1]

        if end_byte > source_bytes_len:
            end_byte = source_bytes_len
        if start_byte > end_byte:
            start_byte = end_byte

        span = SourceSpan(
            start=SourcePosition(byte=start_byte, line=start_line, column=start_col),
            end=SourcePosition(byte=end_byte, line=end_line, column=end_col),
        )

        kind = ts_node.type
        is_named = ts_node.is_named
        is_error = kind == "ERROR" or ts_node.has_error
        is_missing = ts_node.is_missing

        if is_missing and not span.is_empty:
            span = SourceSpan.empty_at(span.start)

        children_list: List[SyntaxNode] = []
        for child_ts in ts_node.children:
            child_field = (
                ts_node.field_name_for_child(child_ts.id)
                if hasattr(ts_node, "field_name_for_child")
                else None
            )
            children_list.append(
                self._convert_node_with_field(child_ts, child_field, source_bytes_len)
            )

        return SyntaxNode(
            kind=kind,
            span=span,
            children=tuple(children_list),
            field_name=field_name,
            is_named=is_named,
            is_error=is_error,
            is_missing=is_missing,
        )
