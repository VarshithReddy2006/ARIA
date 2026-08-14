"""MCP Server for ARIA.

Creates and configures a FastMCP server instance that exposes the
Repository Intelligence Platform through the Model Context Protocol.

All tool implementations delegate to existing services resolved
through backend/dependencies.py. No business logic lives here.
"""

import importlib
import inspect
import logging
import sys
import time
from typing import Any, Dict


# ---------------------------------------------------------------------------
# Pydantic 2.6+ compatibility patch for FastMCP 1.x:
# FastMCP 1.x passes raw annotations (e.g. `owner=Annotated[...]` or `result=str`)
# to `create_model()`. Pydantic 2.6+ requires kwarg field definitions to be 2-tuples
# `(annotation, default)`. We normalize non-tuple kwargs to `(val, ...)` automatically.
# ---------------------------------------------------------------------------
def _patch_pydantic_create_model() -> None:
    try:
        import pydantic
        import pydantic.main

        orig_create_model = pydantic.create_model

        def patched_create_model(
            model_name: str,
            __base__: Any = None,
            __config__: Any = None,
            __doc__: Any = None,
            __module__: Any = None,
            __validators__: Any = None,
            __cls_kwargs__: Any = None,
            __slots__: Any = None,
            **field_definitions: Any,
        ) -> Any:
            fixed_fields: Dict[str, Any] = {}
            for name, val in field_definitions.items():
                if not isinstance(val, tuple):
                    fixed_fields[name] = (val, ...)
                else:
                    fixed_fields[name] = val
            return orig_create_model(
                model_name,
                __base__=__base__,
                __config__=__config__,
                __doc__=__doc__,
                __module__=__module__,
                __validators__=__validators__,
                __cls_kwargs__=__cls_kwargs__,
                __slots__=__slots__,
                **fixed_fields,
            )

        pydantic.create_model = patched_create_model
        pydantic.main.create_model = patched_create_model
    except Exception:
        pass


_patch_pydantic_create_model()


# ---------------------------------------------------------------------------
# Namespace collision guard: our local package is also named `mcp`, which
# shadows the installed `mcp` PyPI SDK. We use importlib to reach the
# real SDK module regardless of local package precedence.
# ---------------------------------------------------------------------------
def _import_fastmcp():
    """Import FastMCP from the installed mcp SDK, bypassing local package shadow."""
    # Temporarily remove our local mcp package from sys.modules cache
    # so importlib can find the installed SDK package.
    _saved = {}
    _to_remove = [key for key in sys.modules if key == "mcp" or key.startswith("mcp.")]
    for key in _to_remove:
        _saved[key] = sys.modules.pop(key)

    # Also temporarily remove local mcp path from sys.path
    import os

    local_mcp_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(local_mcp_dir)

    _path_saved = list(sys.path)
    sys.path = [p for p in sys.path if os.path.abspath(p) != project_root]

    try:
        fastmcp_module = importlib.import_module("mcp.server.fastmcp")
        return fastmcp_module.FastMCP
    finally:
        # Restore everything
        sys.path = _path_saved
        sys.modules.update(_saved)


try:
    FastMCP = _import_fastmcp()
except (ImportError, ModuleNotFoundError):
    # Fallback: if the mcp SDK is not installed, provide a stub so that
    # import-time doesn't crash for tests that mock the server.
    FastMCP = None  # type: ignore[assignment]

logger = logging.getLogger("mcp.server")


def create_server() -> Any:
    """Create and configure the MCP server with all tools, resources, and prompts.

    Returns:
        A configured FastMCP server instance ready to run.

    Raises:
        RuntimeError: If the mcp SDK is not installed.
    """
    if FastMCP is None:
        raise RuntimeError(
            "The 'mcp' Python SDK is not installed. "
            "Install it with: pip install 'mcp[cli]>=1.0.0'"
        )

    from mcp.version import SERVER_NAME, SERVER_VERSION

    # FastMCP dropped the `version` keyword (absent in 1.29). Pass it only when
    # the installed SDK accepts it, so this works across SDK releases instead of
    # raising TypeError at construction time.
    init_kwargs: Dict[str, Any] = {}
    if "version" in inspect.signature(FastMCP.__init__).parameters:
        init_kwargs["version"] = SERVER_VERSION

    server = FastMCP(SERVER_NAME, **init_kwargs)

    # Resolve the dependency bridge now, while we are still on ordinary
    # synchronous startup. Tool bodies import it lazily, and that chain pulls in
    # numpy/ChromaDB/tree-sitter. Because FastMCP invokes synchronous tools
    # directly on the asyncio event loop, paying that cost inside the first
    # tools/call blocks the loop for seconds, stalls the stdio reader, and looks
    # like a transport hang to the client. The legacy stdio server imports its
    # dependencies before entering its read loop for the same reason.
    _warm_dependency_imports()

    # 1. Automate tool discovery and registration (Refinement 1 & 2)
    _register_tools(server)

    # 2. Register resources and prompts
    _register_resources(server)
    _register_prompts(server)

    logger.info("MCP server configured with all tools, resources, and prompts")
    return server


def _warm_dependency_imports() -> None:
    """Import the service bridge eagerly so no tool call pays for it.

    Failures are logged and swallowed: a server that starts and reports tool
    errors is strictly better than one that refuses to start, and the tools
    re-import the same module themselves.
    """
    started = time.perf_counter()
    try:
        import mcp.dependencies  # noqa: F401
        from backend.dependencies import ANALYSIS_STORE, _load_analysis_store
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.warning(
            "Dependency pre-import failed (%s); tools will retry lazily", exc
        )
        return

    # Hydrate persisted repositories, as the FastAPI startup path and the legacy
    # stdio server both do. Without this, every repository-scoped tool reports
    # "not indexed" and list_repositories returns []. Guarded on emptiness so the
    # call stays idempotent across repeated server construction.
    try:
        if not ANALYSIS_STORE:
            _load_analysis_store()
    except Exception as exc:  # pragma: no cover - corrupt store on disk
        logger.warning("Analysis store hydration failed: %s", exc)

    logger.info(
        "Dependency bridge ready in %.2fs; %d repositories available",
        time.perf_counter() - started,
        len(ANALYSIS_STORE),
    )


def _register_tools(server: Any) -> None:
    """Automate tool module discovery and registration."""
    from mcp.tools.discovery import discover_and_register_tools

    discover_and_register_tools(server)


def _register_resources(server: Any) -> None:
    """Register all MCP resources on the server."""
    from mcp.resources.resource_providers import register as register_resources

    register_resources(server)


def _register_prompts(server: Any) -> None:
    """Register all MCP prompts on the server."""
    from mcp.prompts.prompt_templates import register as register_prompts

    register_prompts(server)


def run_mcp_server(transport: str = "stdio") -> None:
    """Entry point for running the MCP server.

    Called by the CLI `repo-intel mcp` command.
    """
    server = create_server()
    if transport == "sse":
        from mcp.transports.sse import run_sse_transport

        run_sse_transport(server)
    else:
        from mcp.transports.stdio import run_stdio_transport

        run_stdio_transport(server)
