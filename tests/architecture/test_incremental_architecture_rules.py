"""Architecture enforcement test for C5 Incremental Indexing package."""

import ast
from pathlib import Path


def test_incremental_package_imports_only_allowed_modules() -> None:
    """Enforce Hexagonal Architecture Rule for C5 Incremental Indexing:
    ria/domain/snapshot, ria/ports/incremental, ria/incremental, and ria/application/incremental MUST NEVER import:
      - ria.infrastructure
      - sqlite3 / postgresql
      - tree-sitter / tree_sitter_*
      - subprocess
      - socket / requests / urllib
    """
    target_dirs = [
        Path("ria/domain/snapshot"),
        Path("ria/ports/incremental"),
        Path("ria/incremental"),
        Path("ria/application/incremental"),
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
