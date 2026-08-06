"""Architecture enforcement test for ria.ports layer."""

import ast
from pathlib import Path


def test_ports_layer_imports_only_allowed_modules() -> None:
    """Enforce Hexagonal Architecture Rule:
    ria/ports/ MUST NEVER import:
      - ria.infrastructure
      - ria.application
      - ria.plugins
    Ports may ONLY import:
      - ria.domain
      - standard library (typing, abc, pathlib, collections.abc, etc.)
    """
    ports_dir = Path("ria/ports")
    assert ports_dir.exists(), "ria/ports directory must exist."

    disallowed_prefixes = (
        "ria.infrastructure",
        "ria.application",
        "ria.plugins",
    )

    for py_file in ports_dir.rglob("*.py"):
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
