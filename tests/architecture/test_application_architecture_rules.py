"""Architecture enforcement test for ria.application package."""

import ast
from pathlib import Path


def test_application_layer_imports_only_allowed_modules() -> None:
    """Enforce Hexagonal Architecture Rule:
    ria/application/ MUST NEVER import:
      - ria.infrastructure
      - tree-sitter / tree_sitter_*
      - sqlite3
      - subprocess
    Application may ONLY import:
      - ria.domain
      - ria.ports
      - ria.application
      - standard library
    """
    app_dir = Path("ria/application")
    assert app_dir.exists(), "ria/application directory must exist."

    disallowed_prefixes = (
        "ria.infrastructure",
        "tree_sitter",
        "sqlite3",
        "subprocess",
    )

    for py_file in app_dir.rglob("*.py"):
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
