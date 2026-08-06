"""SDK compatibility and dependency-policy guards (v1.5.0).

The FastMCP layer targets MCP SDK 1.x. SDK 2.x removed ``mcp.server.fastmcp``
and the ``FastMCP`` class outright, so an unbounded ``mcp[cli]>=1.0.0`` requirement
installs an SDK this codebase cannot import. These tests pin the policy and the
exact SDK surface the code relies on, so either drifting fails the suite instead
of a first-time contributor's install.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "requirements.txt"
PYPROJECT = ROOT / "pyproject.toml"

# Every SDK attribute the implementation touches. Keep this list in step with
# mcp/server.py and mcp/transports/*.py.
REQUIRED_SDK_SURFACE = ["tool", "resource", "prompt", "run"]


def sdk_version() -> str | None:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("mcp")
    except PackageNotFoundError:
        return None


# ---------------------------------------------------------------------------
# Dependency policy
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("manifest", [REQUIREMENTS, PYPROJECT])
def test_mcp_dependency_declares_an_upper_bound(manifest: Path) -> None:
    """An unbounded pin installs SDK 2.x, which cannot import this code."""
    text = manifest.read_text(encoding="utf-8")
    specs = re.findall(r"[\"']?mcp\[cli\][^\"'\n]*", text)
    assert specs, f"no mcp[cli] requirement found in {manifest.name}"
    for spec in specs:
        assert "<2" in spec, (
            f"{manifest.name} pins {spec!r} with no upper bound; a fresh install "
            "will pull SDK 2.x and fail to import mcp.server.fastmcp"
        )


def test_installed_sdk_is_within_the_supported_range() -> None:
    installed = sdk_version()
    if installed is None:
        pytest.skip("mcp SDK not installed")
    major = int(installed.split(".")[0])
    assert major == 1, (
        f"mcp {installed} is installed but this codebase targets SDK 1.x. "
        "See docs/MCP_RELEASE_READINESS.md for the 2.x migration path."
    )


# ---------------------------------------------------------------------------
# SDK surface the implementation depends on
# ---------------------------------------------------------------------------
def test_fastmcp_class_is_importable() -> None:
    """mcp/server.py resolves FastMCP past the local package shadow."""
    from mcp.server import FastMCP

    if FastMCP is None:
        pytest.skip("mcp SDK not installed")
    assert inspect.isclass(FastMCP)


@pytest.mark.parametrize("attribute", REQUIRED_SDK_SURFACE)
def test_required_sdk_surface_exists(attribute: str) -> None:
    from mcp.server import FastMCP

    if FastMCP is None:
        pytest.skip("mcp SDK not installed")
    assert hasattr(FastMCP, attribute), (
        f"FastMCP.{attribute} is gone; the MCP layer depends on it"
    )


def test_server_construction_tolerates_missing_version_kwarg() -> None:
    """FastMCP dropped `version`; construction must not assume it exists."""
    from mcp.server import FastMCP, create_server

    if FastMCP is None:
        pytest.skip("mcp SDK not installed")
    server = create_server()
    assert server is not None


def test_tool_errors_are_reported_via_the_sdk_error_type() -> None:
    """The isError contract depends on the SDK wrapping exceptions in ToolError."""
    from mcp.server import FastMCP

    if FastMCP is None:
        pytest.skip("mcp SDK not installed")
    module = inspect.getmodule(FastMCP)
    assert module is not None
    package = module.__name__.rsplit(".", 1)[0]
    exceptions = __import__(f"{package}.exceptions", fromlist=["ToolError"])
    assert hasattr(exceptions, "ToolError")


def test_stdio_transport_entry_point_is_reachable() -> None:
    """run_mcp_server('stdio') is how clients launch the FastMCP server."""
    from mcp.server import run_mcp_server

    params = inspect.signature(run_mcp_server).parameters
    assert "transport" in params
    assert params["transport"].default == "stdio"


def test_dependency_prewarm_runs_before_the_event_loop() -> None:
    """Regression lock for the transport stall.

    Synchronous tool bodies execute on the asyncio event loop, so the heavy
    import chain must be resolved during construction. If this helper is removed,
    the first tools/call blocks the loop and the transport appears to hang.
    """
    from mcp import server as server_module

    assert hasattr(server_module, "_warm_dependency_imports")
    source = inspect.getsource(server_module.create_server)
    assert "_warm_dependency_imports()" in source


def test_documented_supported_transports_match_the_code() -> None:
    from mcp.version import SUPPORTED_TRANSPORTS

    assert set(SUPPORTED_TRANSPORTS) == {"stdio", "sse"}
