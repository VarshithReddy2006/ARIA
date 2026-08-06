"""FastMCP behavioural parity with the legacy stdio server (MCP Stability v1.2).

Covers the five behavioural gaps closed in this milestone:

* Phase 1 - ``get_impact_analysis`` accepts the deprecated ``file_path`` alias.
* Phase 2 - business failures raise, so FastMCP emits ``isError`` rather than a
  successful result whose payload merely looks like an error.
* Phase 3 - arguments are validated before any service call.
* Phase 4 - ``get_symbol_references`` tolerates ``Optional[List]``.
* Phase 5 - failure messages carry no tracebacks, paths or source locations.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable
from unittest.mock import MagicMock, patch

import pytest

from backend.mcp_server import TOOLS as LEGACY_TOOLS
from mcp.errors import ToolFailure, ToolInputError

# Markers that must never appear in a client-visible failure message. Mirrors
# the sweep in scripts/mcp_validate.py so both implementations face one bar.
INTERNAL_MARKERS = {
    "traceback header": "Traceback (most recent call last)",
    "source line": 'File "',
    "drive-letter path": ":\\",
    "site-packages path": "site-packages",
    "interpreter frame": ", line ",
}


class Capture:
    """Minimal server double that captures registered callables."""

    def __init__(self) -> None:
        self.tools: dict[str, Callable[..., Any]] = {}
        self.resources: dict[str, Callable[..., Any]] = {}
        self.prompts: dict[str, Callable[..., Any]] = {}

    def tool(
        self, *a: Any, **k: Any
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.tools[fn.__name__] = fn
            return fn

        return deco

    def resource(
        self, uri: str, *a: Any, **k: Any
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.resources[uri] = fn
            return fn

        return deco

    def prompt(
        self, *a: Any, **k: Any
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.prompts[fn.__name__] = fn
            return fn

        return deco


@pytest.fixture
def tools() -> Capture:
    from mcp.tools.discovery import discover_and_register_tools

    cap = Capture()
    discover_and_register_tools(cap)
    return cap


def assert_clean(message: str) -> None:
    leaked = [label for label, needle in INTERNAL_MARKERS.items() if needle in message]
    assert not leaked, f"failure message leaked {leaked}: {message!r}"


# ---------------------------------------------------------------------------
# Phase 1 - deprecated parameter alias
# ---------------------------------------------------------------------------
class TestImpactAnalysisAlias:
    @pytest.fixture
    def service(self):
        from services.impact_analysis_service import ImpactAnalysisService

        svc = MagicMock(spec=ImpactAnalysisService)
        result = MagicMock()
        result.model_dump.return_value = {"affected_files": ["a.py"]}
        svc.analyze_change.return_value = result
        return svc

    def _call(self, tools: Capture, service: Any, **kwargs: Any) -> Any:
        with patch(
            "mcp.dependencies.get_impact_analysis_service", return_value=service
        ):
            return tools.tools["get_impact_analysis"](
                owner="acme", repo="widget", **kwargs
            )

    def test_new_parameter_is_used(self, tools: Capture, service: Any) -> None:
        payload = json.loads(
            self._call(tools, service, change_description="rename auth")
        )
        assert payload == {"affected_files": ["a.py"]}
        service.analyze_change.assert_called_once_with("acme/widget", "rename auth")

    def test_deprecated_alias_still_works(self, tools: Capture, service: Any) -> None:
        """Existing clients passing file_path must keep working unchanged."""
        payload = json.loads(self._call(tools, service, file_path="core/auth.py"))
        assert payload == {"affected_files": ["a.py"]}
        service.analyze_change.assert_called_once_with("acme/widget", "core/auth.py")

    def test_new_parameter_wins_when_both_supplied(
        self, tools: Capture, service: Any
    ) -> None:
        self._call(
            tools, service, change_description="preferred", file_path="ignored.py"
        )
        service.analyze_change.assert_called_once_with("acme/widget", "preferred")

    def test_neither_parameter_is_invalid_params(
        self, tools: Capture, service: Any
    ) -> None:
        with pytest.raises(ToolInputError, match="Missing required argument"):
            self._call(tools, service)
        service.analyze_change.assert_not_called()

    def test_deprecation_warning_is_logged_not_returned(
        self, tools: Capture, service: Any, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The notice belongs in the operator's log, never in the client payload."""
        with caplog.at_level(logging.WARNING):
            raw = self._call(tools, service, file_path="core/auth.py")
        assert "deprecated" in caplog.text
        assert "deprecated" not in raw

    def test_metadata_documents_the_alias(self) -> None:
        from mcp.tools import analysis_tools

        meta = next(
            m for m in analysis_tools.METADATA if m.name == "get_impact_analysis"
        )
        assert "change" in meta.description.lower()


# ---------------------------------------------------------------------------
# Phase 2 - MCP-compliant error semantics
# ---------------------------------------------------------------------------
class TestErrorSemantics:
    def test_missing_repository_raises(self, tools: Capture) -> None:
        with patch("mcp.dependencies.ANALYSIS_STORE", {}):
            with pytest.raises(ToolFailure, match="is not indexed"):
                tools.tools["get_repository_summary"]("acme", "missing")

    def test_missing_graph_raises(self, tools: Capture) -> None:
        from services.call_graph_service import CallGraphService

        svc = MagicMock(spec=CallGraphService)
        svc.load_summary.return_value = None
        with patch("mcp.dependencies.get_call_graph_service", return_value=svc):
            with pytest.raises(ToolFailure, match="No call graph indexed"):
                tools.tools["get_call_graph"]("acme", "widget")

    def test_missing_symbol_raises(self, tools: Capture) -> None:
        from services.symbol_service import SymbolService

        svc = MagicMock(spec=SymbolService)
        svc.get_definition.return_value = None
        with patch("mcp.dependencies.get_symbol_service", return_value=svc):
            with pytest.raises(ToolFailure, match="not found in repo"):
                tools.tools["get_symbol_definition"]("acme", "widget", "nope")

    def test_missing_symbol_index_raises(self, tools: Capture) -> None:
        from services.symbol_service import SymbolService

        svc = MagicMock(spec=SymbolService)
        svc.get_file_symbols.return_value = None
        with patch("mcp.dependencies.get_symbol_service", return_value=svc):
            with pytest.raises(ToolFailure, match="No symbol index found"):
                tools.tools["get_file_symbols"]("acme", "widget", "a.py")

    def test_retrieval_failure_is_redacted_and_raised(self, tools: Capture) -> None:
        from services.retrieval_service import RetrievalService

        svc = MagicMock(spec=RetrievalService)
        svc.retrieve_and_answer.side_effect = RuntimeError(
            r"C:\secrets\creds.db unreadable"
        )
        with patch("mcp.dependencies.get_retrieval_service", return_value=svc):
            with pytest.raises(ToolFailure) as caught:
                tools.tools["query_codebase"]("acme", "widget", "what is this")
        message = str(caught.value)
        assert "secrets" not in message and "creds.db" not in message
        assert "internal error" in message
        assert_clean(message)

    def test_no_tool_returns_an_error_shaped_success(self, tools: Capture) -> None:
        """Regression lock: a tool must never encode failure in a success payload."""
        with patch("mcp.dependencies.ANALYSIS_STORE", {}):
            try:
                raw = tools.tools["get_repository_summary"]("acme", "missing")
            except ToolFailure:
                return  # correct
        assert False, f"returned a success payload instead of raising: {raw!r}"

    def test_success_still_returns_json(self, tools: Capture) -> None:
        with patch("mcp.dependencies.ANALYSIS_STORE", {"acme/widget": {}}):
            assert json.loads(tools.tools["list_repositories"]()) == ["acme/widget"]


# ---------------------------------------------------------------------------
# Phase 3 - validation runs before the service layer
# ---------------------------------------------------------------------------
class TestParameterValidation:
    @pytest.mark.parametrize(
        "owner, repo, expected",
        [
            ("", "widget", "must not be empty"),
            ("   ", "widget", "must not be empty"),
            ("acme", "", "must not be empty"),
            (None, "widget", "Missing required argument"),
            (123, "widget", "must be a string, got int"),
            (["acme"], "widget", "must be a string, got list"),
        ],
    )
    def test_invalid_arguments_never_reach_the_service(
        self, tools: Capture, owner: Any, repo: Any, expected: str
    ) -> None:
        from services.call_graph_service import CallGraphService

        tripwire = MagicMock(spec=CallGraphService)
        with patch("mcp.dependencies.get_call_graph_service", return_value=tripwire):
            with pytest.raises(ToolInputError, match=expected):
                tools.tools["get_call_graph"](owner, repo)
        tripwire.load_summary.assert_not_called()

    def test_whitespace_is_trimmed_before_dispatch(self, tools: Capture) -> None:
        from services.call_graph_service import CallGraphService

        svc = MagicMock(spec=CallGraphService)
        svc.load_summary.return_value = MagicMock(model_dump=lambda: {})
        with patch("mcp.dependencies.get_call_graph_service", return_value=svc):
            tools.tools["get_call_graph"]("  acme ", " widget  ")
        svc.load_summary.assert_called_once_with("acme/widget")

    def test_invalid_top_k_rejected(self, tools: Capture) -> None:
        with pytest.raises(ToolInputError, match="top_k"):
            tools.tools["semantic_search"]("acme", "widget", "q", top_k=0)

    def test_invalid_export_format_rejected(self, tools: Capture) -> None:
        from services.report.composer import ReportComposer

        tripwire = MagicMock(spec=ReportComposer)
        with patch("mcp.dependencies.get_report_composer", return_value=tripwire):
            with pytest.raises(ToolInputError, match="format"):
                tools.tools["export_report"]("acme", "widget", format="pdf")
        tripwire.compose_report.assert_not_called()


# ---------------------------------------------------------------------------
# Phase 4 - Optional[List] handling
# ---------------------------------------------------------------------------
class TestSymbolReferencesNoneGuard:
    @pytest.mark.parametrize("returned", [None, []])
    def test_absent_references_yield_empty_list(
        self, tools: Capture, returned: Any
    ) -> None:
        from services.symbol_service import SymbolService

        svc = MagicMock(spec=SymbolService)
        svc.get_references.return_value = returned
        with patch("mcp.dependencies.get_symbol_service", return_value=svc):
            raw = tools.tools["get_symbol_references"]("acme", "widget", "f")
        assert json.loads(raw) == []

    def test_present_references_are_serialised(self, tools: Capture) -> None:
        from services.symbol_service import SymbolService

        ref = MagicMock()
        ref.model_dump.return_value = {"file_path": "a.py"}
        svc = MagicMock(spec=SymbolService)
        svc.get_references.return_value = [ref]
        with patch("mcp.dependencies.get_symbol_service", return_value=svc):
            raw = tools.tools["get_symbol_references"]("acme", "widget", "f")
        assert json.loads(raw) == [{"file_path": "a.py"}]


# ---------------------------------------------------------------------------
# Phase 5 - traceback hygiene
# ---------------------------------------------------------------------------
class TestTracebackHygiene:
    def test_unexpected_errors_are_redacted_across_every_tool(
        self, tools: Capture
    ) -> None:
        """Force an unexpected failure in each tool and sweep the message."""
        boom = RuntimeError(r"C:\Users\dev\project\secret.py line 42 exploded")
        getters = [
            "get_call_graph_service",
            "get_symbol_service",
            "get_retrieval_service",
            "get_report_composer",
            "get_api_surface_service",
            "get_graph_serializer",
            "get_workspace_service",
            "get_dead_code_service",
        ]
        patches = [patch(f"mcp.dependencies.{g}", side_effect=boom) for g in getters]
        for p in patches:
            p.start()
        try:
            for name, fn in sorted(tools.tools.items()):
                if name in {"list_repositories", "analyze_repository"}:
                    continue
                kwargs = {
                    p: ("acme" if p == "owner" else "widget" if p == "repo" else "x")
                    for p in fn.__code__.co_varnames[: fn.__code__.co_argcount]
                }
                try:
                    fn(**kwargs)
                except (ToolFailure, ToolInputError) as exc:
                    assert_clean(str(exc))
                except Exception as exc:  # noqa: BLE001
                    pytest.fail(
                        f"{name} raised un-normalised {type(exc).__name__}: {exc}"
                    )
        finally:
            for p in patches:
                p.stop()

    def test_full_traceback_is_logged_internally(
        self, tools: Capture, caplog: pytest.LogCaptureFixture
    ) -> None:
        from services.call_graph_service import CallGraphService

        svc = MagicMock(spec=CallGraphService)
        svc.load_summary.side_effect = RuntimeError("internal detail")
        with patch("mcp.dependencies.get_call_graph_service", return_value=svc):
            with caplog.at_level(logging.ERROR):
                with pytest.raises(ToolFailure):
                    tools.tools["get_call_graph"]("acme", "widget")
        assert "Traceback (most recent call last)" in caplog.text
        assert "internal detail" in caplog.text

    def test_debug_env_var_reenables_traceback(
        self, tools: Capture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Respects the same MCP_DEBUG_ERRORS gate as the legacy server."""
        from services.call_graph_service import CallGraphService

        monkeypatch.setenv("MCP_DEBUG_ERRORS", "1")
        svc = MagicMock(spec=CallGraphService)
        svc.load_summary.side_effect = RuntimeError("internal detail")
        with patch("mcp.dependencies.get_call_graph_service", return_value=svc):
            with pytest.raises(ToolFailure) as caught:
                tools.tools["get_call_graph"]("acme", "widget")
        assert "Traceback (most recent call last)" in str(caught.value)


# ---------------------------------------------------------------------------
# Phase 6 - message parity with the legacy server
# ---------------------------------------------------------------------------
class TestLegacyMessageParity:
    """Identical diagnostics for identical conditions, so clients see one story."""

    def test_not_indexed_wording_matches_legacy(self, tools: Capture) -> None:
        from backend.mcp_server import execute_tool

        with pytest.raises(ValueError) as legacy:
            execute_tool(
                "get_repository_summary",
                {"owner": "acme", "repo": "missing"},
                {},
                None,
                None,
                None,
                None,
            )
        with patch("mcp.dependencies.ANALYSIS_STORE", {}):
            with pytest.raises(ToolFailure) as fast:
                tools.tools["get_repository_summary"]("acme", "missing")
        assert str(legacy.value) == str(fast.value)

    def test_call_graph_wording_matches_legacy(self, tools: Capture) -> None:
        from backend.mcp_server import execute_tool
        from services.call_graph_service import CallGraphService

        legacy_svc = MagicMock(spec=CallGraphService)
        legacy_svc.load_summary.return_value = None
        with pytest.raises(ValueError) as legacy:
            execute_tool(
                "get_call_graph",
                {"owner": "acme", "repo": "widget"},
                {},
                None,
                legacy_svc,
                None,
                None,
            )
        fast_svc = MagicMock(spec=CallGraphService)
        fast_svc.load_summary.return_value = None
        with patch("mcp.dependencies.get_call_graph_service", return_value=fast_svc):
            with pytest.raises(ToolFailure) as fast:
                tools.tools["get_call_graph"]("acme", "widget")
        assert str(legacy.value) == str(fast.value)

    def test_validation_wording_matches_legacy(self, tools: Capture) -> None:
        from backend.mcp_server import validate_tool_arguments, InvalidParams

        with pytest.raises(InvalidParams) as legacy:
            validate_tool_arguments("get_call_graph", {"owner": 123, "repo": "widget"})
        with pytest.raises(ToolInputError) as fast:
            tools.tools["get_call_graph"](123, "widget")
        # Legacy prefixes "Invalid params:" at the JSON-RPC layer; FastMCP has to
        # embed it in the message because it cannot emit a -32602 envelope.
        assert str(legacy.value) in str(fast.value)


# ---------------------------------------------------------------------------
# End-to-end through the real SDK
# ---------------------------------------------------------------------------
def test_business_failure_surfaces_as_sdk_tool_error() -> None:
    """The real FastMCP wraps a raised exception, which lowlevel flags isError.

    Skipped when the SDK is absent, since create_server() then cannot run.
    """
    import asyncio

    from mcp.server import FastMCP, create_server

    if FastMCP is None:
        pytest.skip("mcp SDK not installed")

    from services.call_graph_service import CallGraphService

    server = create_server()
    svc = MagicMock(spec=CallGraphService)
    svc.load_summary.return_value = None

    async def drive() -> str:
        with patch("mcp.dependencies.get_call_graph_service", return_value=svc):
            try:
                await server.call_tool(
                    "get_call_graph", {"owner": "acme", "repo": "widget"}
                )
            except Exception as exc:
                return f"{type(exc).__name__}: {exc}"
        return ""

    outcome = asyncio.run(drive())
    assert outcome.startswith("ToolError"), outcome
    assert "No call graph indexed" in outcome
    assert_clean(outcome)


def test_sdk_reports_all_legacy_tools() -> None:
    """The SDK-advertised tool list must still cover every legacy tool."""
    import asyncio

    from mcp.server import FastMCP, create_server

    if FastMCP is None:
        pytest.skip("mcp SDK not installed")

    server = create_server()
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert {t["name"] for t in LEGACY_TOOLS} <= names
