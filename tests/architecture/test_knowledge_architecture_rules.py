"""Architecture enforcement test for C8 Knowledge Layer package."""

import ast
from pathlib import Path


def test_knowledge_package_imports_only_allowed_modules() -> None:
    """Enforce Hexagonal Architecture Rule for C8 Knowledge Layer:
    ria/domain/knowledge, ria/ports/knowledge, ria/knowledge, and ria/application/knowledge MUST NEVER import:
      - ria.infrastructure
      - sqlite3 / psycopg2
      - tree-sitter / tree_sitter_*
      - subprocess
      - socket / requests / urllib / openai / anthropic / langchain / transformers (outside explicit adapters)
      - ria.resolution, ria.query, ria.search, ria.incremental
    """
    target_dirs = [
        Path("ria/domain/knowledge"),
        Path("ria/ports/knowledge"),
        Path("ria/knowledge"),
        Path("ria/application/knowledge"),
    ]

    disallowed_prefixes = (
        "ria.infrastructure",
        "sqlite3",
        "psycopg2",
        "tree_sitter",
        "subprocess",
        "socket",
        "requests",
        "urllib",
        "openai",
        "anthropic",
        "langchain",
        "transformers",
        "ria.resolution",
        "ria.query",
        "ria.search",
        "ria.incremental",
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
                                f"Import '{alias.name}' violates hexagonal boundary rule."
                            )
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        for disallowed in disallowed_prefixes:
                            assert not node.module.startswith(disallowed), (
                                f"Architecture Violation in {py_file}: "
                                f"ImportFrom '{node.module}' violates hexagonal boundary rule."
                            )
