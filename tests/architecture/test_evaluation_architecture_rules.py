"""Architecture enforcement test for ria.evaluation package."""

import ast
from pathlib import Path


def test_evaluation_layer_imports_only_allowed_modules() -> None:
    """Enforce Architecture Rule:
    ria/evaluation/ may ONLY import:
      - ria.domain
      - ria.ports
      - ria.config
      - ria.application
      - ria.plugins
      - standard library
    """
    eval_dir = Path("ria/evaluation")
    assert eval_dir.exists(), "ria/evaluation directory must exist."

    # evaluation is cross-cutting, but domain & ports must never import evaluation
    domain_dir = Path("ria/domain")
    ports_dir = Path("ria/ports")

    for target_dir in [domain_dir, ports_dir]:
        for py_file in target_dir.rglob("*.py"):
            code = py_file.read_text(encoding="utf-8")
            tree = ast.parse(code, filename=str(py_file))

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert not alias.name.startswith("ria.evaluation"), (
                            f"Architecture Violation in {py_file}: "
                            f"Import '{alias.name}' leaks evaluation into core domain/ports boundary."
                        )
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        assert not node.module.startswith("ria.evaluation"), (
                            f"Architecture Violation in {py_file}: "
                            f"ImportFrom '{node.module}' leaks evaluation into core domain/ports boundary."
                        )
