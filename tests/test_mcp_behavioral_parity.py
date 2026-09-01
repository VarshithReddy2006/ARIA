"""FastMCP behavioural parity with the legacy stdio server (MCP Stability v1.2).

Covers the behavioral guarantees:
* Phase 1 - get_impact_analysis accepts the deprecated file_path alias.
* Phase 2 - business failures raise, so FastMCP emits isError rather than a
  successful result whose payload merely looks like an error.
* Phase 3 - arguments are validated before any network/client call.
* Phase 4 - get_symbol_references tolerates empty/absent reference lists.
* Phase 5 - failure messages carry no tracebacks, paths, or source locations.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable
from unittest.mock import MagicMock, patch

import pytest

from backend.mcp_server import TOOLS as LEGACY_TOOLS
from mcp.aria_client import AriaAPIClient
from mcp.errors import ToolFailure, ToolInputError

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
    def client(self):
        client = MagicMock(spec=AriaAPIClient)
        client.post.return_value = {"affected_files": ["a.py"]}
        return client

    def _call(self, tools: Capture, client: Any, **kwargs: Any) -> Any:
        with patch("mcp.dependencies.get_aria_client", return_value=client):
            return tools.tools["get_impact_analysis"](
                owner="acme", repo="widget", **kwargs
            )

    def test_new_parameter_is_used(self, tools: Capture, client: Any) -> None:
        payload = json.loads(
            self._call(tools, client, change_description="rename auth")
        )
        assert payload == {"affected_files": ["a.py"]}
        client.post.assert_called_once_with(
            "/api/v1/impact-analysis",
            json={"repo": "acme/widget", "issue": "rename auth"},
        )

    def test_deprecated_alias_still_works(self, tools: Capture, client: Any) -> None:
        payload = json.loads(self._call(tools, client, file_path="core/auth.py"))
        assert payload == {"affected_files": ["a.py"]}
        client.post.assert_called_once_with(
            "/api/v1/impact-analysis",
            json={"repo": "acme/widget", "issue": "core/auth.py"},
        )

    def test_new_parameter_wins_when_both_supplied(
        self, tools: Capture, client: Any
    ) -> None:
        self._call(
            tools, client, change_description="preferred", file_path="ignored.py"
        )
        client.post.assert_called_once_with(
            "/api/v1/impact-analysis",
            json={"repo": "acme/widget", "issue": "preferred"},
        )

    def test_neither_parameter_is_invalid_params(
        self, tools: Capture, client: Any
    ) -> None:
        with pytest.raises(ToolInputError, match="Missing required argument"):
            self._call(tools, client)
        client.post.assert_not_called()

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
        client = MagicMock(spec=AriaAPIClient)
        client.get.side_effect = ToolFailure(
            "Repository 'acme/missing' is not indexed."
        )
        with patch("mcp.dependencies.get_aria_client", return_value=client):
            with pytest.raises(ToolFailure, match="is not indexed"):
                tools.tools["get_repository_summary"]("acme", "missing")

    def test_missing_graph_raises(self, tools: Capture) -> None:
        client = MagicMock(spec=AriaAPIClient)
        client.get.side_effect = ToolFailure("No call graph indexed for 'acme/widget'.")
        with patch("mcp.dependencies.get_aria_client", return_value=client):
            with pytest.raises(ToolFailure, match="No call graph indexed"):
                tools.tools["get_call_graph"]("acme", "widget")

    def test_missing_symbol_raises(self, tools: Capture) -> None:
        client = MagicMock(spec=AriaAPIClient)
        client.get.side_effect = ToolFailure(
            "Symbol 'nope' not found in repo 'acme/widget'."
        )
        with patch("mcp.dependencies.get_aria_client", return_value=client):
            with pytest.raises(ToolFailure, match="not found in repo"):
                tools.tools["get_symbol_definition"]("acme", "widget", "nope")

    def test_missing_symbol_index_raises(self, tools: Capture) -> None:
        client = MagicMock(spec=AriaAPIClient)
        client.get.side_effect = ToolFailure("No symbol index found for 'acme/widget'.")
        with patch("mcp.dependencies.get_aria_client", return_value=client):
            with pytest.raises(ToolFailure, match="No symbol index found"):
                tools.tools["get_file_symbols"]("acme", "widget", "a.py")

    def test_retrieval_failure_is_redacted_and_raised(self, tools: Capture) -> None:
        client = MagicMock(spec=AriaAPIClient)
        client.post.side_effect = RuntimeError(r"C:\secrets\creds.db unreadable")
        with patch("mcp.dependencies.get_aria_client", return_value=client):
            with pytest.raises(ToolFailure) as caught:
                tools.tools["query_codebase"]("acme", "widget", "what is this")
        message = str(caught.value)
        assert "secrets" not in message and "creds.db" not in message
        assert "internal error" in message
        assert_clean(message)

    def test_no_tool_returns_an_error_shaped_success(self, tools: Capture) -> None:
        client = MagicMock(spec=AriaAPIClient)
        client.get.side_effect = ToolFailure(
            "Repository 'acme/missing' is not indexed."
        )
        with patch("mcp.dependencies.get_aria_client", return_value=client):
            try:
                raw = tools.tools["get_repository_summary"]("acme", "missing")
            except ToolFailure:
                return
        assert False, f"returned a success payload instead of raising: {raw!r}"

    def test_success_still_returns_json(self, tools: Capture) -> None:
        client = MagicMock(spec=AriaAPIClient)
        client.get.return_value = [{"name": "acme/widget"}]
        with patch("mcp.dependencies.get_aria_client", return_value=client):
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
        client = MagicMock(spec=AriaAPIClient)
        with patch("mcp.dependencies.get_aria_client", return_value=client):
            with pytest.raises(ToolInputError, match=expected):
                tools.tools["get_call_graph"](owner, repo)
        client.get.assert_not_called()

    def test_whitespace_is_trimmed_before_dispatch(self, tools: Capture) -> None:
        client = MagicMock(spec=AriaAPIClient)
        client.get.return_value = {}
        with patch("mcp.dependencies.get_aria_client", return_value=client):
            tools.tools["get_call_graph"]("  acme ", " widget  ")
        client.get.assert_called_once_with("/api/v1/call-graph/acme/widget")

    def test_invalid_top_k_rejected(self, tools: Capture) -> None:
        with pytest.raises(ToolInputError, match="top_k"):
            tools.tools["semantic_search"]("acme", "widget", "q", top_k=0)

    def test_invalid_export_format_rejected(self, tools: Capture) -> None:
        client = MagicMock(spec=AriaAPIClient)
        with patch("mcp.dependencies.get_aria_client", return_value=client):
            with pytest.raises(ToolInputError, match="format"):
                tools.tools["export_report"]("acme", "widget", format="pdf")
        client.get.assert_not_called()


# ---------------------------------------------------------------------------
# Phase 4 - Optional[List] handling
# ---------------------------------------------------------------------------
class TestSymbolReferencesNoneGuard:
    @pytest.mark.parametrize("returned", [None, [], {}])
    def test_absent_references_yield_empty_list(
        self, tools: Capture, returned: Any
    ) -> None:
        client = MagicMock(spec=AriaAPIClient)
        client.get.return_value = returned
        with patch("mcp.dependencies.get_aria_client", return_value=client):
            raw = tools.tools["get_symbol_references"]("acme", "widget", "f")
        assert json.loads(raw) == []

    def test_present_references_are_serialised(self, tools: Capture) -> None:
        client = MagicMock(spec=AriaAPIClient)
        client.get.return_value = [{"file_path": "a.py"}]
        with patch("mcp.dependencies.get_aria_client", return_value=client):
            raw = tools.tools["get_symbol_references"]("acme", "widget", "f")
        assert json.loads(raw) == [{"file_path": "a.py"}]


# ---------------------------------------------------------------------------
# Phase 5 - traceback hygiene
# ---------------------------------------------------------------------------
class TestTracebackHygiene:
    def test_unexpected_errors_are_redacted_across_every_tool(
        self, tools: Capture
    ) -> None:
        client = MagicMock(spec=AriaAPIClient)
        client.get.side_effect = RuntimeError(
            r"C:\Users\dev\project\secret.py line 42 exploded"
        )
        client.post.side_effect = RuntimeError(
            r"C:\Users\dev\project\secret.py line 42 exploded"
        )

        with patch("mcp.dependencies.get_aria_client", return_value=client):
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

    def test_full_traceback_is_logged_internally(
        self, tools: Capture, caplog: pytest.LogCaptureFixture
    ) -> None:
        client = MagicMock(spec=AriaAPIClient)
        client.get.side_effect = RuntimeError("internal detail")
        with patch("mcp.dependencies.get_aria_client", return_value=client):
            with caplog.at_level(logging.ERROR):
                with pytest.raises(ToolFailure):
                    tools.tools["get_call_graph"]("acme", "widget")
        assert "Traceback (most recent call last)" in caplog.text
        assert "internal detail" in caplog.text

    def test_debug_env_var_reenables_traceback(
        self, tools: Capture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MCP_DEBUG_ERRORS", "1")
        client = MagicMock(spec=AriaAPIClient)
        client.get.side_effect = RuntimeError("internal detail")
        with patch("mcp.dependencies.get_aria_client", return_value=client):
            with pytest.raises(ToolFailure) as caught:
                tools.tools["get_call_graph"]("acme", "widget")
        assert "Traceback (most recent call last)" in str(caught.value)


# ---------------------------------------------------------------------------
# Phase 6 - message parity with the legacy server
# ---------------------------------------------------------------------------
class TestLegacyMessageParity:
    """Identical diagnostics for identical conditions, so clients see one story."""

    def test_validation_wording_matches_legacy(self, tools: Capture) -> None:
        from backend.mcp_server import validate_tool_arguments, InvalidParams

        with pytest.raises(InvalidParams) as legacy:
            validate_tool_arguments("get_call_graph", {"owner": 123, "repo": "widget"})
        with pytest.raises(ToolInputError) as fast:
            tools.tools["get_call_graph"](123, "widget")
        assert str(legacy.value) in str(fast.value)


# ---------------------------------------------------------------------------
# End-to-end through the real SDK
# ---------------------------------------------------------------------------
def test_business_failure_surfaces_as_sdk_tool_error() -> None:
    import asyncio

    from mcp.server import FastMCP, create_server

    if FastMCP is None:
        pytest.skip("mcp SDK not installed")

    server = create_server()
    client = MagicMock(spec=AriaAPIClient)
    client.get.side_effect = ToolFailure("No call graph indexed for 'acme/widget'.")

    async def drive() -> str:
        with patch("mcp.dependencies.get_aria_client", return_value=client):
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
    import asyncio

    from mcp.server import FastMCP, create_server

    if FastMCP is None:
        pytest.skip("mcp SDK not installed")

    server = create_server()
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert {t["name"] for t in LEGACY_TOOLS} <= names
