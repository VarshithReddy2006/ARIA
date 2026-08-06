"""Tests for TreeSitterAdapter."""

from __future__ import annotations

import pytest

from ria.domain.models.parser_identity import ComponentVersion
from ria.domain.models.syntax_tree import SyntaxTree
from ria.infrastructure.parser.tree_sitter_adapter import TreeSitterAdapter
from ria.ports.parser import ParserPort

CONTENT_HASH = "sha256:" + "a" * 64


class TestTreeSitterAdapter:
    def test_implements_parser_port(self) -> None:
        adapter = TreeSitterAdapter()
        assert isinstance(adapter, ParserPort)

    def test_parse_python_source(self) -> None:
        adapter = TreeSitterAdapter()
        code = b"def add(a: int, b: int) -> int:\n    return a + b\n"
        tree = adapter.parse_bytes(
            code,
            language="python",
            content_hash=CONTENT_HASH,
        )

        assert isinstance(tree, SyntaxTree)
        assert tree.language == "python"
        assert tree.content_hash == CONTENT_HASH
        assert tree.root.kind == "module"
        assert tree.node_count > 0
        assert not tree.has_errors

    @pytest.mark.parametrize(
        "language,code",
        [
            ("javascript", b"function greet(name) { return 'Hello ' + name; }"),
            ("typescript", b"interface User { id: number; name: string; }"),
            ("tsx", b"const App = () => <div>Hello</div>;"),
        ],
    )
    def test_parse_js_ts_languages(self, language: str, code: bytes) -> None:
        adapter = TreeSitterAdapter()
        tree = adapter.parse_bytes(code, language=language, content_hash=CONTENT_HASH)

        assert isinstance(tree, SyntaxTree)
        assert tree.language == language
        assert tree.node_count > 0
        assert not tree.has_errors

    def test_parse_determinism(self) -> None:
        adapter = TreeSitterAdapter()
        code = b"class Calculator:\n    def double(self, x):\n        return x * 2\n"

        tree1 = adapter.parse_bytes(code, language="python", content_hash=CONTENT_HASH)
        tree2 = adapter.parse_bytes(code, language="python", content_hash=CONTENT_HASH)

        assert tree1.structural_digest() == tree2.structural_digest()
        assert tree1 == tree2

    def test_parser_version(self) -> None:
        adapter = TreeSitterAdapter()
        version = adapter.parser_version("python")

        assert isinstance(version, ComponentVersion)
        assert version.name == "tree-sitter-python"
        assert version.version == "0.21.0"

    def test_unsupported_language_raises(self) -> None:
        adapter = TreeSitterAdapter()
        with pytest.raises(ValueError, match="unsupported language"):
            adapter.parse_bytes(b"content", language="cobol", content_hash=CONTENT_HASH)

        with pytest.raises(ValueError, match="unsupported language"):
            adapter.parser_version("cobol")

    def test_parse_invalid_syntax_yields_error_nodes(self) -> None:
        adapter = TreeSitterAdapter()
        # Invalid python code: missing colon and indented body
        bad_code = b"def broken_fn(\n"
        tree = adapter.parse_bytes(
            bad_code, language="python", content_hash=CONTENT_HASH
        )

        assert isinstance(tree, SyntaxTree)
        assert tree.has_errors
        assert len(tree.error_nodes) > 0
