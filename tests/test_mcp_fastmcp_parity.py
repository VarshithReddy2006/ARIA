"""FastMCP parity, contract and API-drift tests (MCP Stability v1.1).

The FastMCP layer shipped calls to service methods that did not exist. Unit
tests missed it because every double was a bare ``MagicMock``, which answers to
any attribute. These tests close that hole three ways:

1. A static guard resolves every ``service.method()`` call in ``mcp/`` against
   the real class, so drift fails the suite without executing anything.
2. A runtime guard registers the real tools against the real services and
   invokes the cheap read-only ones, so an ``AttributeError`` cannot hide.
3. Contract tests pin the eight tools shared with the validated legacy stdio
   server to identical names and parameters.
"""

from __future__ import annotations

import ast
import inspect
import json
import typing
from pathlib import Path
from typing import Any, Callable

import pytest

import mcp.dependencies as mcp_deps
from backend.mcp_server import TOOLS as LEGACY_TOOLS

MCP_ROOT = Path(__file__).resolve().parents[1] / "mcp"

# Tools that clone, index, call an LLM, or load an embedding model. Excluded
# from the runtime sweep only; the static guard still covers their call sites.
EXPENSIVE_TOOLS = {
    "analyze_repository",   # clones a repository over the network
    "get_dead_code",        # builds dependency + call graphs
    "query_codebase",       # LLM round trip
    "semantic_search",      # loads the embedding model
    "generate_report",      # composes every analysis
    "export_report",        # composes then renders
    "get_impact_analysis",  # LLM-assisted change prediction
}

# The eight tools the legacy stdio server exposes and FastMCP must match.
SHARED_TOOLS = {t["name"] for t in LEGACY_TOOLS}


class RecordingServer:
    """Captures tools/resources/prompts registered by the real register() hooks."""

    def __init__(self) -> None:
        self.tools: dict[str, Callable[..., Any]] = {}
        self.resources: dict[str, Callable[..., Any]] = {}
        self.prompts: dict[str, Callable[..., Any]] = {}

    def tool(self, *a: Any, **k: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.tools[fn.__name__] = fn
            return fn

        return deco

    def resource(self, uri: str, *a: Any, **k: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.resources[uri] = fn
            return fn

        return deco

    def prompt(self, *a: Any, **k: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.prompts[fn.__name__] = fn
            return fn

        return deco


@pytest.fixture(scope="module")
def registered() -> RecordingServer:
    """Register every real tool module, unmocked, via the real discovery path."""
    from mcp.tools.discovery import discover_and_register_tools
    from mcp.resources.resource_providers import register as register_resources

    server = RecordingServer()
    discover_and_register_tools(server)
    register_resources(server)
    return server


# ---------------------------------------------------------------------------
# 1. Static API-drift guard
# ---------------------------------------------------------------------------
def _service_class(getter_name: str) -> type | None:
    """Resolve a dependency getter's return type without constructing it."""
    getter = getattr(mcp_deps, getter_name, None)
    if getter is None or not callable(getter):
        return None
    try:
        hints = typing.get_type_hints(getter)
    except Exception:
        return None
    ret = hints.get("return")
    return ret if isinstance(ret, type) else None


def _leaf_functions(tree: ast.AST) -> list[ast.FunctionDef]:
    """Return functions containing no nested function, i.e. the tool bodies.

    Scoping matters: ``service`` is rebound to a different getter in each tool,
    so a module-wide variable map would attribute calls to the wrong class.
    """
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            nested = [
                n
                for n in ast.walk(node)
                if isinstance(n, ast.FunctionDef) and n is not node
            ]
            if not nested:
                out.append(node)
    return out


def _collect_calls() -> list[tuple[str, str, str, int]]:
    """Find every (file, getter, method, lineno) service call under mcp/."""
    found: list[tuple[str, str, str, int]] = []
    for path in sorted(MCP_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for fn in _leaf_functions(tree):
            var_to_getter: dict[str, str] = {}
            for node in ast.walk(fn):
                # svc = get_x_service()
                if (
                    isinstance(node, ast.Assign)
                    and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name)
                    and node.value.func.id.startswith("get_")
                ):
                    var_to_getter[node.targets[0].id] = node.value.func.id
            for node in ast.walk(fn):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                    continue
                target, method = node.func.value, node.func.attr
                # svc.method(...)
                if isinstance(target, ast.Name) and target.id in var_to_getter:
                    found.append(
                        (path.name, var_to_getter[target.id], method, node.lineno)
                    )
                # get_x_service().method(...)
                elif (
                    isinstance(target, ast.Call)
                    and isinstance(target.func, ast.Name)
                    and target.func.id.startswith("get_")
                ):
                    found.append((path.name, target.func.id, method, node.lineno))
    return found


def test_static_guard_finds_service_calls() -> None:
    """Guard the guard: if extraction silently breaks, everything below passes."""
    calls = _collect_calls()
    assert len(calls) >= 10, f"AST extraction found only {len(calls)} calls; it is broken"


def test_every_service_method_called_by_fastmcp_exists() -> None:
    """No call in mcp/ may name a method the service does not define.

    This is the check that would have caught get_graph_summary,
    retrieve_and_evaluate, analyze_impact, classify, serialize, clone_repo and
    get_all_symbols before they reached runtime.
    """
    broken: list[str] = []
    for filename, getter, method, lineno in _collect_calls():
        cls = _service_class(getter)
        if cls is None:
            continue  # getter has no resolvable annotation; nothing to assert
        if not hasattr(cls, method):
            broken.append(f"{filename}:{lineno} {cls.__name__}.{method}() does not exist")
    assert not broken, "obsolete service calls in FastMCP:\n  " + "\n  ".join(broken)


@pytest.mark.parametrize(
    "module_path, cls_name, removed",
    [
        ("services.call_graph_service", "CallGraphService", "get_graph_summary"),
        ("services.retrieval_service", "RetrievalService", "retrieve_and_evaluate"),
        ("services.symbol_service", "SymbolService", "get_all_symbols"),
        ("services.impact_analysis_service", "ImpactAnalysisService", "analyze_impact"),
        ("services.api_surface_service", "APISurfaceService", "classify"),
        ("services.graph_serializer", "GraphSerializer", "serialize"),
        ("services.github_service", "GitHubService", "clone_repo"),
        ("services.retrieval_engine", "StructuralRetrievalEngine", "search"),
    ],
)
def test_removed_methods_stay_removed(module_path: str, cls_name: str, removed: str) -> None:
    """Pins the removals. If one is reintroduced, revisit the call site instead."""
    mod = __import__(module_path, fromlist=[cls_name])
    assert not hasattr(getattr(mod, cls_name), removed), (
        f"{cls_name}.{removed} reappeared; the FastMCP replacement may now be wrong"
    )


# ---------------------------------------------------------------------------
# 2. Runtime guard against real services
# ---------------------------------------------------------------------------
def test_all_tool_modules_register_without_error(registered: RecordingServer) -> None:
    """Discovery is fault-isolated, so a broken module would silently vanish."""
    assert len(registered.tools) >= 15, sorted(registered.tools)
    assert SHARED_TOOLS <= set(registered.tools), sorted(SHARED_TOOLS - set(registered.tools))


@pytest.mark.parametrize("owner, repo", [("zz-no-such-owner", "zz-no-such-repo")])
def test_read_only_tools_never_raise_attributeerror(
    registered: RecordingServer, owner: str, repo: str
) -> None:
    """Invoke each cheap read-only tool against the real services.

    An unindexed repository must produce a clean JSON error, never a Python
    AttributeError leaking through the tool's blanket except handler. This is
    the runtime counterpart to the static guard.
    """
    from mcp.errors import ToolFailure, ToolInputError

    failures: list[str] = []
    for name, fn in sorted(registered.tools.items()):
        if name in EXPENSIVE_TOOLS:
            continue
        params = inspect.signature(fn).parameters
        kwargs: dict[str, Any] = {}
        for pname in params:
            if pname == "owner":
                kwargs[pname] = owner
            elif pname == "repo":
                kwargs[pname] = repo
            else:
                kwargs[pname] = "x"
        try:
            raw = fn(**kwargs)
        except (ToolFailure, ToolInputError) as expected:
            # Since v1.2 a business failure is a raised exception, which FastMCP
            # renders as isError=True. That is the correct outcome here, but the
            # message must still be free of internals.
            if "has no attribute" in str(expected):
                failures.append(f"{name} leaked an AttributeError: {expected}")
            continue
        except Exception as exc:
            failures.append(
                f"{name} raised un-normalised {type(exc).__name__}: {exc}"
            )
            continue
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            failures.append(f"{name} returned non-JSON: {exc}")
            continue
        blob = json.dumps(payload)
        if "has no attribute" in blob or "object has no attribute" in blob:
            failures.append(f"{name} leaked an AttributeError: {blob[:160]}")
    assert not failures, "runtime API drift:\n  " + "\n  ".join(failures)


def test_call_graph_resource_uses_current_api(registered: RecordingServer) -> None:
    """The resource providers drifted independently of the tools; pin them too."""
    from mcp.errors import ToolFailure
    from mcp.resources.namespace import TEMPLATE_CALL_GRAPH, TEMPLATE_SYMBOLS

    for template in (TEMPLATE_CALL_GRAPH, TEMPLATE_SYMBOLS):
        try:
            payload = json.dumps(
                json.loads(registered.resources[template]("zz-owner", "zz-repo"))
            )
        except ToolFailure as expected:
            payload = str(expected)
        assert "has no attribute" not in payload, payload


# ---------------------------------------------------------------------------
# 3. Legacy <-> FastMCP contract parity
# ---------------------------------------------------------------------------
def test_shared_tool_names_match_legacy(registered: RecordingServer) -> None:
    missing = SHARED_TOOLS - set(registered.tools)
    assert not missing, f"FastMCP is missing legacy tools: {sorted(missing)}"


@pytest.mark.parametrize("tool_name", sorted(SHARED_TOOLS))
def test_shared_tool_parameters_match_legacy(
    registered: RecordingServer, tool_name: str
) -> None:
    """Identical parameter names, so a client can swap implementations."""
    legacy = next(t for t in LEGACY_TOOLS if t["name"] == tool_name)
    legacy_params = set(legacy["inputSchema"].get("properties", {}))
    fast_params = {
        p for p in inspect.signature(registered.tools[tool_name]).parameters
    }
    assert fast_params == legacy_params, (
        f"{tool_name}: legacy={sorted(legacy_params)} fastmcp={sorted(fast_params)}"
    )


@pytest.mark.parametrize("tool_name", sorted(SHARED_TOOLS))
def test_shared_tool_required_arguments_match_legacy(
    registered: RecordingServer, tool_name: str
) -> None:
    """A legacy-required argument must not be optional in FastMCP."""
    legacy = next(t for t in LEGACY_TOOLS if t["name"] == tool_name)
    required = set(legacy["inputSchema"].get("required", []))
    params = inspect.signature(registered.tools[tool_name]).parameters
    optional = {n for n, p in params.items() if p.default is not inspect.Parameter.empty}
    assert not (required & optional), (
        f"{tool_name}: {sorted(required & optional)} required by legacy but optional here"
    )


# ---------------------------------------------------------------------------
# 4. Metadata drift
# ---------------------------------------------------------------------------
def test_declared_metadata_matches_registered_tools(registered: RecordingServer) -> None:
    """Every METADATA entry must name a real tool, and vice versa."""
    import importlib
    import pkgutil

    import mcp.tools

    declared: set[str] = set()
    for _, mod_name, is_pkg in pkgutil.iter_modules(
        mcp.tools.__path__, mcp.tools.__name__ + "."
    ):
        if is_pkg:
            continue
        mod = importlib.import_module(mod_name)
        for meta in getattr(mod, "METADATA", []) or []:
            declared.add(meta.name)

    registered_names = set(registered.tools)
    assert declared - registered_names == set(), (
        f"metadata declares tools that are not registered: {sorted(declared - registered_names)}"
    )
    assert registered_names - declared == set(), (
        f"tools registered without metadata: {sorted(registered_names - declared)}"
    )
