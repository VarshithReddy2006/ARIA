"""Architecture enforcement test for C3 Fact Store storage ports."""

import ast
from pathlib import Path


def test_fact_store_port_imports_only_allowed_modules() -> None:
    """Enforce Architecture Rule:
    ria/ports/storage MUST NEVER import ria.infrastructure or concrete database adapters.
    """
    port_dir = Path("ria/ports/storage")
    assert port_dir.exists(), "ria/ports/storage directory must exist."

    disallowed_prefixes = (
        "ria.infrastructure",
        "sqlite3",
        "psycopg2",
        "subprocess",
    )

    for py_file in port_dir.rglob("*.py"):
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
