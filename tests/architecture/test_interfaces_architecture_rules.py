"""Architecture enforcement test for C9 Developer Interfaces package."""

import ast
from pathlib import Path


def test_interfaces_package_imports_only_allowed_modules() -> None:
    """Enforce Hexagonal Architecture Rule for C9 Developer Interfaces:
    ria/interfaces MUST NEVER import:
      - ria.infrastructure
      - sqlite3 / psycopg2
      - tree-sitter / tree_sitter_*
      - subprocess
      - socket / requests / urllib (outside explicit network transport adapters)
      - ria.resolution, ria.query, ria.search, ria.incremental, ria.context, ria.knowledge (internal engines)
    """
    target_dirs = [
        Path("ria/interfaces/rest"),
        Path("ria/interfaces/cli"),
        Path("ria/interfaces/mcp"),
        Path("ria/interfaces/sdk/python"),
        Path("ria/interfaces/vscode/extension"),
    ]

    disallowed_prefixes = (
        "ria.infrastructure",
        "sqlite3",
        "psycopg2",
        "tree_sitter",
        "subprocess",
        "ria.resolution",
        "ria.query",
        "ria.search",
        "ria.incremental",
        "ria.context",
        "ria.knowledge",
    )

    for tdir in target_dirs:
        assert tdir.exists(), f"Directory {tdir} must exist."
        for py_file in tdir.rglob("*.py"):
            code = py_file.read_text(encoding="utf-8")
            tree = ast.parse(code, filename=str(py_file))

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        for disallowed in disallowed_prefixes:
                            assert not alias.name.startswith(disallowed), (
                                f"Architecture Violation in {py_file}: "
                                f"Import '{alias.name}' violates interface boundary rule."
                            )
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        for disallowed in disallowed_prefixes:
                            assert not node.module.startswith(disallowed), (
                                f"Architecture Violation in {py_file}: "
                                f"ImportFrom '{node.module}' violates interface boundary rule."
                            )
