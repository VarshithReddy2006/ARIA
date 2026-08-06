"""Unit tests for Python, TypeScript, and JavaScript Tree-sitter Parser Plugins."""

from ria.domain.index.value_objects import ASTNode, FilePath
from ria.plugins import (
    JavaScriptTreeSitterPlugin,
    PythonTreeSitterPlugin,
    TypeScriptTreeSitterPlugin,
)


def test_python_tree_sitter_parser() -> None:
    parser = PythonTreeSitterPlugin()
    fp = FilePath(relative_path="sample.py")
    code = b"def add(a: int, b: int) -> int:\n    return a + b\n"

    result = parser.parse(fp, code)
    assert result.is_success
    assert not result.has_syntax_errors
    assert result.total_nodes > 1
    assert isinstance(result.ast_root_node, ASTNode)
    assert result.ast_root_node.type == "module"


def test_typescript_tree_sitter_parser() -> None:
    parser = TypeScriptTreeSitterPlugin()
    fp = FilePath(relative_path="sample.ts")
    code = b"interface User {\n  id: string;\n  name: string;\n}\nconst u: User = { id: '1', name: 'Alice' };\n"

    result = parser.parse(fp, code)
    assert result.is_success
    assert not result.has_syntax_errors
    assert result.total_nodes > 1
    assert isinstance(result.ast_root_node, ASTNode)
    assert result.ast_root_node.type == "program"


def test_javascript_tree_sitter_parser() -> None:
    parser = JavaScriptTreeSitterPlugin()
    fp = FilePath(relative_path="sample.js")
    code = b"function greet(name) {\n  console.log('Hello ' + name);\n}\n"

    result = parser.parse(fp, code)
    assert result.is_success
    assert not result.has_syntax_errors
    assert result.total_nodes > 1
    assert isinstance(result.ast_root_node, ASTNode)
    assert result.ast_root_node.type == "program"


def test_python_parser_malformed_syntax() -> None:
    parser = PythonTreeSitterPlugin()
    fp = FilePath(relative_path="broken.py")
    code = b"def broken_fn(:\n    return 42\n"

    result = parser.parse(fp, code)
    assert result.is_success  # Tree-sitter succeeds parsing even malformed syntax
    assert result.has_syntax_errors
    assert result.error_message is not None
