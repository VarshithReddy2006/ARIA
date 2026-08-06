"""Architecture enforcement test for ria.plugins package."""

import ast
from pathlib import Path


def test_plugins_layer_imports_only_allowed_modules() -> None:
    """Enforce Hexagonal Architecture Rule:
    ria/plugins/ MUST NEVER import:
      - ria.infrastructure
      - ria.application
    Plugins may ONLY import:
      - ria.domain
      - ria.ports
      - standard library & tree-sitter libraries
    """
    plugins_dir = Path("ria/plugins")
    assert plugins_dir.exists(), "ria/plugins directory must exist."

    disallowed_prefixes = (
        "ria.infrastructure",
        "ria.application",
    )

    for py_file in plugins_dir.rglob("*.py"):
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
