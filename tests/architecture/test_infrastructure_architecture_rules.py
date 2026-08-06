"""Architecture enforcement test for ria.infrastructure layer."""

import ast
from pathlib import Path


def test_domain_and_ports_never_import_infrastructure() -> None:
    """Enforce Hexagonal Architecture Rule:
    ria/domain/ and ria/ports/ MUST NEVER import:
      - ria.infrastructure
      - ria.config
    """
    targets = [Path("ria/domain"), Path("ria/ports")]

    disallowed_prefixes = (
        "ria.infrastructure",
        "ria.config",
    )

    for target_dir in targets:
        for py_file in target_dir.rglob("*.py"):
            code = py_file.read_text(encoding="utf-8")
            tree = ast.parse(code, filename=str(py_file))

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        for disallowed in disallowed_prefixes:
                            assert not alias.name.startswith(disallowed), (
                                f"Architecture Violation in {py_file}: "
                                f"Import '{alias.name}' leaks infrastructure into domain/ports boundary."
                            )
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        for disallowed in disallowed_prefixes:
                            assert not node.module.startswith(disallowed), (
                                f"Architecture Violation in {py_file}: "
                                f"ImportFrom '{node.module}' leaks infrastructure into domain/ports boundary."
                            )
