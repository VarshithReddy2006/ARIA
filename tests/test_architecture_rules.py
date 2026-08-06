"""Automated CI Guard: Enforce Architectural Inversion Rules (R-007).

Asserts that lower-level layers (services, core, agents, memory, models, storage)
never import from the top-level delivery layer (backend).
"""

import ast
import os
from pathlib import Path
import pytest

DOMAIN_MODULES = [
    "services",
    "core",
    "agents",
    "memory",
    "models",
    "storage",
]

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_imported_modules(file_path: Path) -> set[str]:
    """Parse python AST and extract imported top-level module names."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))
    except Exception:
        return set()

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
    return imported


@pytest.mark.parametrize("domain_dir", DOMAIN_MODULES)
def test_no_backend_imports_in_domain_layer(domain_dir: str):
    """Verify that domain modules contain ZERO imports of backend.*."""
    target_dir = PROJECT_ROOT / domain_dir
    if not target_dir.exists():
        pytest.skip(f"Directory {domain_dir} does not exist.")

    violations = []
    for py_file in target_dir.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        imports = get_imported_modules(py_file)
        if "backend" in imports:
            rel_path = py_file.relative_to(PROJECT_ROOT)
            violations.append(str(rel_path))

    assert (
        len(violations) == 0
    ), f"Architecture Violation! Found illegal 'backend' imports in domain layer:\n" + "\n".join(
        f"  - {v}" for v in violations
    )
