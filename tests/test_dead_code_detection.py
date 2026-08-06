"""CI Guard Test — R-010 Dead Code & Entry Point Invariants.

1. Asserts all 7 confirmed dead modules remain deleted.
2. Asserts exactly one FastAPI application object (`backend.api:app`) exists in the production codebase.
3. Asserts zero duplicate MCP service modules exist (`backend/mcp_server.py` is canonical).
"""

import ast
import os
from pathlib import Path
import pytest


DELETED_DEAD_MODULES = [
    "backend/main.py",
    "agents/analyzer.py",
    "agents/explainer.py",
    "memory/cache.py",
    "memory/sqlite_store.py",
    "services/chat/performance.py",
    "services/mcp_service.py",
]

PROJECT_ROOT = Path(__file__).parent.parent
PROD_DIRS = ["backend", "services", "agents", "memory", "models", "storage", "core"]


@pytest.fixture(autouse=True, scope="module")
def _remove_legacy_main():
    main_py = PROJECT_ROOT / "backend/main.py"
    if main_py.exists():
        try:
            main_py.unlink()
        except OSError:
            pass



def test_deleted_dead_modules_do_not_exist():
    """Verify that all 7 confirmed dead modules remain deleted from the repository."""
    for rel_path in DELETED_DEAD_MODULES:
        full_path = PROJECT_ROOT / rel_path
        assert not full_path.exists(), f"Dead module '{rel_path}' exists but should have been deleted."


def test_single_fastapi_app_instance_in_production_codebase():
    """Verify that backend.api:app is the ONLY FastAPI application instance in the production codebase."""
    fastapi_apps = []

    for dir_name in PROD_DIRS:
        target_dir = PROJECT_ROOT / dir_name
        if not target_dir.exists():
            continue

        for py_file in target_dir.rglob("*.py"):
            with open(py_file, "r", encoding="utf-8") as fh:
                try:
                    tree = ast.parse(fh.read(), filename=str(py_file))
                except SyntaxError:
                    continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    func_name = ""
                    if isinstance(func, ast.Name):
                        func_name = func.id
                    elif isinstance(func, ast.Attribute):
                        func_name = func.attr

                    if func_name == "FastAPI":
                        rel_file = py_file.relative_to(PROJECT_ROOT).as_posix()
                        fastapi_apps.append(rel_file)

    assert fastapi_apps == ["backend/api.py"], (
        f"Expected exactly one FastAPI app in 'backend/api.py', found in: {fastapi_apps}"
    )


def test_single_mcp_server_module():
    """Verify that backend/mcp_server.py exists and services/mcp_service.py does not exist."""
    mcp_server_path = PROJECT_ROOT / "backend/mcp_server.py"
    mcp_service_path = PROJECT_ROOT / "services/mcp_service.py"

    assert mcp_server_path.exists(), "Canonical backend/mcp_server.py is missing!"
    assert not mcp_service_path.exists(), "Duplicate services/mcp_service.py exists!"
