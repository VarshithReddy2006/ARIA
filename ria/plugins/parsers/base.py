"""Base Tree-sitter Parser Plugin abstraction."""

from typing import Any

import tree_sitter
from ria.domain.index.units import ParserResult
from ria.domain.index.value_objects import ASTNode, FilePath
from ria.plugins.core.exceptions import ParserError
from ria.plugins.core.interface import AbstractParser


class BaseTreeSitterPlugin(AbstractParser):
    """Abstract base tree-sitter plugin converting C-level tree-sitter AST nodes into immutable domain ASTNode objects."""

    def __init__(self, language_ptr: Any, language_name: str) -> None:
        self._ts_language = tree_sitter.Language(language_ptr, language_name)
        self._parser = tree_sitter.Parser()
        self._parser.set_language(self._ts_language)

    def _convert_node(self, ts_node: Any, code: bytes) -> tuple[ASTNode, int, bool]:
        """Recursively convert a tree_sitter.Node into an immutable domain ASTNode.

        Returns (ASTNode, node_count, has_error).
        """
        node_type = str(ts_node.type)
        start_point = ts_node.start_point
        end_point = ts_node.end_point

        # Line numbers in domain are 1-indexed (tree-sitter is 0-indexed)
        start_line = int(start_point[0]) + 1
        start_col = int(start_point[1])
        end_line = int(end_point[0]) + 1
        end_col = int(end_point[1])

        has_error = ts_node.has_error or ts_node.is_missing or (node_type == "ERROR")

        total_nodes = 1
        child_nodes: list[ASTNode] = []

        for child in ts_node.children:
            c_ast, c_count, c_err = self._convert_node(child, code)
            child_nodes.append(c_ast)
            total_nodes += c_count
            if c_err:
                has_error = True

        attrs: tuple[tuple[str, str], ...] = ()
        if not ts_node.children:
            text_val = code[ts_node.start_byte : ts_node.end_byte].decode(
                "utf-8", errors="ignore"
            )
            attrs = (("text", text_val),)

        domain_ast = ASTNode(
            type=node_type,
            start_line=start_line,
            start_col=start_col,
            end_line=end_line,
            end_col=end_col,
            attributes=attrs,
            children=tuple(child_nodes),
        )
        return domain_ast, total_nodes, has_error

    def parse(self, path: FilePath, code: bytes) -> ParserResult:
        """Parse source code bytes into immutable AST ParserResult."""
        try:
            tree = self._parser.parse(code)
            root_node = tree.root_node
            domain_ast, total_nodes, has_error = self._convert_node(root_node, code)
            err_msg = "AST contains syntax errors" if has_error else None

            return ParserResult(
                ast_root_node=domain_ast,
                total_nodes=total_nodes,
                has_syntax_errors=has_error,
                is_success=True,
                error_message=err_msg,
            )
        except Exception as err:
            raise ParserError(f"Failed to parse '{path.relative_path}': {err}") from err
