"""Unit tests for the legacy stdio JSON-RPC MCP server (MCP Stability v1.0).

Drives `run_mcp_server()` in-process by scripting stdin and capturing stdout,
so the full request/response cycle is exercised without spawning a subprocess.
Covers BUG-001 through BUG-008.
"""

from __future__ import annotations

import importlib
import io
import json
import sys
from typing import Any

import pytest

import backend.dependencies as deps
from backend.mcp_server import run_mcp_server


@pytest.fixture(autouse=True)
def _live_dependencies_module() -> None:
    """Rebind ``deps`` to whatever ``backend.dependencies`` is currently loaded.

    ``run_mcp_server`` imports its singletons at call time, so it always sees
    the module registered in ``sys.modules``. If another test has evicted the
    ``backend.*`` entries, the reference captured at import time above becomes
    stale, and patching it would have no effect on the code under test.
    Re-resolving here keeps these tests independent of execution order.
    """
    global deps
    deps = importlib.import_module("backend.dependencies")


def drive(monkeypatch: pytest.MonkeyPatch, *frames: str) -> list[dict[str, Any]]:
    """Feed raw lines to the server loop; return parsed stdout frames."""
    monkeypatch.setattr(sys, "stdin", io.StringIO("".join(f + "\n" for f in frames)))
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    run_mcp_server()
    return [json.loads(line) for line in buf.getvalue().splitlines() if line.strip()]


def call(tool: str, arguments: Any, req_id: int = 1) -> str:
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        }
    )


def payload(frame: dict[str, Any]) -> Any:
    """Decode the JSON document a tool returns inside result.content[0].text."""
    return json.loads(frame["result"]["content"][0]["text"])


@pytest.fixture
def empty_store(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Isolate ANALYSIS_STORE so tests never touch the real on-disk store."""
    store: dict[str, Any] = {}
    monkeypatch.setattr(deps, "ANALYSIS_STORE", store)
    monkeypatch.setattr(deps, "_load_analysis_store", lambda: None)
    return store


# ---------------------------------------------------------------------------
# BUG-001 — analysis store hydration
# ---------------------------------------------------------------------------
class TestStoreHydration:
    def test_store_is_hydrated_on_startup(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The stdio server must hydrate persisted repositories, as FastAPI does."""
        store: dict[str, Any] = {}
        monkeypatch.setattr(deps, "ANALYSIS_STORE", store)
        monkeypatch.setattr(
            deps, "_load_analysis_store", lambda: store.update({"acme/widget": {}})
        )

        frames = drive(monkeypatch, call("list_repositories", {}))
        assert payload(frames[0]) == ["acme/widget"]

    def test_hydration_skipped_when_store_already_populated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Idempotent: a populated store is never reloaded or clobbered."""
        store: dict[str, Any] = {"acme/widget": {}}
        calls: list[int] = []
        monkeypatch.setattr(deps, "ANALYSIS_STORE", store)
        monkeypatch.setattr(deps, "_load_analysis_store", lambda: calls.append(1))

        frames = drive(monkeypatch, call("list_repositories", {}))
        assert calls == [], "loader ran against an already-hydrated store"
        assert payload(frames[0]) == ["acme/widget"]

    def test_repeated_launches_do_not_duplicate_entries(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two sequential server runs leave the store byte-identical."""
        store: dict[str, Any] = {}
        monkeypatch.setattr(deps, "ANALYSIS_STORE", store)
        monkeypatch.setattr(
            deps, "_load_analysis_store", lambda: store.update({"acme/widget": {}})
        )

        first = payload(drive(monkeypatch, call("list_repositories", {}))[0])
        second = payload(drive(monkeypatch, call("list_repositories", {}))[0])
        assert first == second == ["acme/widget"]


# ---------------------------------------------------------------------------
# BUG-003 — tools calling methods that do not exist on their services
# ---------------------------------------------------------------------------
class TestServiceMethodBinding:
    """The handler must call the real public API, verified against the live classes."""

    def test_call_graph_uses_existing_service_method(self) -> None:
        from services.call_graph_service import CallGraphService

        assert hasattr(CallGraphService, "load_summary")
        assert not hasattr(CallGraphService, "get_graph_summary")

    def test_retrieval_uses_existing_service_method(self) -> None:
        from services.retrieval_service import RetrievalService

        assert hasattr(RetrievalService, "retrieve_and_answer")
        assert not hasattr(RetrievalService, "retrieve_and_evaluate")

    def test_get_call_graph_returns_summary(
        self, monkeypatch: pytest.MonkeyPatch, empty_store: dict[str, Any]
    ) -> None:
        class FakeCallGraph:
            def load_summary(self, repo_name: str) -> Any:
                assert repo_name == "acme/widget"
                return type(
                    "S", (), {"model_dump": lambda self: {"nodes": 3, "edges": 2}}
                )()

        monkeypatch.setattr(deps, "call_graph_service", FakeCallGraph())
        frames = drive(
            monkeypatch, call("get_call_graph", {"owner": "acme", "repo": "widget"})
        )
        assert payload(frames[0]) == {"nodes": 3, "edges": 2}

    def test_query_codebase_returns_answer(
        self, monkeypatch: pytest.MonkeyPatch, empty_store: dict[str, Any]
    ) -> None:
        class FakeRetrieval:
            def retrieve_and_answer(
                self, repo_name: str, question: str
            ) -> dict[str, Any]:
                assert (repo_name, question) == ("acme/widget", "what is this")
                return {
                    "answer": "A",
                    "sources": [],
                    "confidence": 0.9,
                    "verified": True,
                }

        monkeypatch.setattr(deps, "retrieval_service", FakeRetrieval())
        frames = drive(
            monkeypatch,
            call(
                "query_codebase",
                {"owner": "acme", "repo": "widget", "query": "what is this"},
            ),
        )
        assert payload(frames[0]) == {
            "answer": "A",
            "sources": [],
            "confidence": 0.9,
            "verified": True,
        }


# ---------------------------------------------------------------------------
# BUG-002 — traceback leakage
# ---------------------------------------------------------------------------
class TestErrorRedaction:
    def test_domain_error_message_is_forwarded_without_traceback(
        self, monkeypatch: pytest.MonkeyPatch, empty_store: dict[str, Any]
    ) -> None:
        monkeypatch.delenv("MCP_DEBUG_ERRORS", raising=False)
        frames = drive(
            monkeypatch,
            call("get_repository_summary", {"owner": "acme", "repo": "missing"}),
        )
        blob = json.dumps(frames[0])
        assert "not indexed" in blob, "actionable domain text must survive"
        assert "Traceback (most recent call last)" not in blob
        assert ".py" not in blob, "no source file names may appear"

    def test_unexpected_error_is_redacted(
        self, monkeypatch: pytest.MonkeyPatch, empty_store: dict[str, Any]
    ) -> None:
        """A non-ValueError must not surface its message to the client."""

        class Exploding:
            def load_summary(self, repo_name: str) -> Any:
                raise RuntimeError(r"C:\secrets\token.db is unreadable")

        monkeypatch.delenv("MCP_DEBUG_ERRORS", raising=False)
        monkeypatch.setattr(deps, "call_graph_service", Exploding())
        frames = drive(
            monkeypatch, call("get_call_graph", {"owner": "acme", "repo": "widget"})
        )
        blob = json.dumps(frames[0])
        assert "secrets" not in blob and "token.db" not in blob
        assert "internal error" in frames[0]["result"]["content"][0]["text"]

    def test_debug_env_var_reenables_traceback(
        self, monkeypatch: pytest.MonkeyPatch, empty_store: dict[str, Any]
    ) -> None:
        monkeypatch.setenv("MCP_DEBUG_ERRORS", "1")
        frames = drive(
            monkeypatch,
            call("get_repository_summary", {"owner": "acme", "repo": "missing"}),
        )
        assert (
            "Traceback (most recent call last)"
            in frames[0]["result"]["content"][0]["text"]
        )

    def test_traceback_is_still_logged_internally(
        self,
        monkeypatch: pytest.MonkeyPatch,
        empty_store: dict[str, Any],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.delenv("MCP_DEBUG_ERRORS", raising=False)
        with caplog.at_level("ERROR"):
            drive(
                monkeypatch, call("get_repository_summary", {"owner": "a", "repo": "b"})
            )
        assert "Traceback (most recent call last)" in caplog.text


# ---------------------------------------------------------------------------
# BUG-005 — parameter validation (-32602 before business logic)
# ---------------------------------------------------------------------------
class TestParameterValidation:
    @pytest.mark.parametrize(
        "arguments, expected",
        [
            ({}, "Missing required argument(s): owner, repo."),
            ({"owner": "acme"}, "Missing required argument(s): repo."),
            ({"owner": 123, "repo": "widget"}, "must be a string, got int"),
            ({"owner": "acme", "repo": ""}, "must not be empty"),
            ({"owner": "acme", "repo": "   "}, "must not be empty"),
            ({"owner": None, "repo": "widget"}, "must be a string, got NoneType"),
            ({"owner": ["a"], "repo": "widget"}, "must be a string, got list"),
        ],
    )
    def test_invalid_arguments_rejected_with_32602(
        self,
        monkeypatch: pytest.MonkeyPatch,
        empty_store: dict[str, Any],
        arguments: Any,
        expected: str,
    ) -> None:
        frames = drive(monkeypatch, call("get_repository_summary", arguments))
        assert frames[0]["error"]["code"] == -32602
        assert expected in frames[0]["error"]["message"]

    def test_non_object_arguments_rejected(
        self, monkeypatch: pytest.MonkeyPatch, empty_store: dict[str, Any]
    ) -> None:
        frames = drive(monkeypatch, call("list_repositories", "not-an-object"))
        assert frames[0]["error"]["code"] == -32602
        assert "must be a JSON object" in frames[0]["error"]["message"]

    def test_unknown_tool_rejected_with_32602(
        self, monkeypatch: pytest.MonkeyPatch, empty_store: dict[str, Any]
    ) -> None:
        frames = drive(monkeypatch, call("no_such_tool", {}))
        assert frames[0]["error"]["code"] == -32602
        assert "Unknown tool" in frames[0]["error"]["message"]

    def test_service_layer_never_invoked_on_invalid_params(
        self, monkeypatch: pytest.MonkeyPatch, empty_store: dict[str, Any]
    ) -> None:
        """The whole point of -32602: business logic must not run."""
        touched: list[str] = []

        class Tripwire:
            def load_summary(self, repo_name: str) -> Any:
                touched.append(repo_name)
                return None

        monkeypatch.setattr(deps, "call_graph_service", Tripwire())
        drive(monkeypatch, call("get_call_graph", {"owner": 1, "repo": 2}))
        assert touched == []

    def test_unknown_properties_are_ignored_not_rejected(
        self, monkeypatch: pytest.MonkeyPatch, empty_store: dict[str, Any]
    ) -> None:
        """Forward compatibility: an extra field must not fail the call."""
        empty_store["acme/widget"] = {"analysis": {"x": 1}, "architecture": {"y": 2}}
        frames = drive(
            monkeypatch,
            call(
                "get_repository_summary",
                {"owner": "acme", "repo": "widget", "future_hint": [1, 2]},
            ),
        )
        assert "result" in frames[0]

    def test_whitespace_is_trimmed_before_dispatch(
        self, monkeypatch: pytest.MonkeyPatch, empty_store: dict[str, Any]
    ) -> None:
        seen: list[str] = []

        class Recorder:
            def load_summary(self, repo_name: str) -> Any:
                seen.append(repo_name)
                return type("S", (), {"model_dump": lambda self: {}})()

        monkeypatch.setattr(deps, "call_graph_service", Recorder())
        drive(
            monkeypatch,
            call("get_call_graph", {"owner": "  acme ", "repo": " widget  "}),
        )
        assert seen == ["acme/widget"]


# ---------------------------------------------------------------------------
# BUG-006 — MCP-compliant tool errors (isError, not JSON-RPC error)
# ---------------------------------------------------------------------------
class TestToolErrorShape:
    def test_business_failure_returns_iserror_result(
        self, monkeypatch: pytest.MonkeyPatch, empty_store: dict[str, Any]
    ) -> None:
        frames = drive(
            monkeypatch,
            call("get_repository_summary", {"owner": "acme", "repo": "missing"}),
        )
        result = frames[0]["result"]
        assert "error" not in frames[0], "business failure must not be a JSON-RPC error"
        assert result["isError"] is True
        assert result["content"][0]["type"] == "text"
        assert "not indexed" in result["content"][0]["text"]

    def test_successful_call_has_no_iserror_flag(
        self, monkeypatch: pytest.MonkeyPatch, empty_store: dict[str, Any]
    ) -> None:
        frames = drive(monkeypatch, call("list_repositories", {}))
        assert not frames[0]["result"].get("isError")

    @pytest.mark.parametrize(
        "frame, expected_code",
        [
            ('{"jsonrpc":"2.0","id":1,"method":"nope/nope"}', -32601),
            (
                '{"jsonrpc":"2.0","id":1,"method":"tools/call",'
                '"params":{"name":"get_call_graph","arguments":{}}}',
                -32602,
            ),
        ],
    )
    def test_protocol_failures_still_use_jsonrpc_errors(
        self,
        monkeypatch: pytest.MonkeyPatch,
        empty_store: dict[str, Any],
        frame: str,
        expected_code: int,
    ) -> None:
        frames = drive(monkeypatch, frame)
        assert frames[0]["error"]["code"] == expected_code


# ---------------------------------------------------------------------------
# BUG-004 — get_symbol_references Optional[List] handling
# ---------------------------------------------------------------------------
class TestSymbolReferencesNoneHandling:
    @pytest.mark.parametrize("returned", [None, []])
    def test_absent_references_yield_empty_list(
        self,
        monkeypatch: pytest.MonkeyPatch,
        empty_store: dict[str, Any],
        returned: Any,
    ) -> None:
        class FakeSymbols:
            def get_references(self, repo_name: str, symbol_name: str) -> Any:
                return returned

        monkeypatch.setattr(deps, "symbol_service", FakeSymbols())
        frames = drive(
            monkeypatch,
            call(
                "get_symbol_references", {"owner": "a", "repo": "b", "symbol_name": "f"}
            ),
        )
        assert not frames[0]["result"].get("isError"), "None must not raise"
        assert payload(frames[0]) == []

    def test_present_references_are_serialised(
        self, monkeypatch: pytest.MonkeyPatch, empty_store: dict[str, Any]
    ) -> None:
        class FakeSymbols:
            def get_references(self, repo_name: str, symbol_name: str) -> Any:
                return [
                    type("S", (), {"model_dump": lambda self: {"file_path": "a.py"}})()
                ]

        monkeypatch.setattr(deps, "symbol_service", FakeSymbols())
        frames = drive(
            monkeypatch,
            call(
                "get_symbol_references", {"owner": "a", "repo": "b", "symbol_name": "f"}
            ),
        )
        assert payload(frames[0]) == [{"file_path": "a.py"}]


# ---------------------------------------------------------------------------
# BUG-007 — parse errors must carry "id": null
# ---------------------------------------------------------------------------
class TestParseErrorCompliance:
    def test_parse_error_includes_null_id(
        self, monkeypatch: pytest.MonkeyPatch, empty_store: dict[str, Any]
    ) -> None:
        frames = drive(monkeypatch, '{"jsonrpc":"2.0","id":1,"method":"tools/list"')
        assert frames[0]["error"]["code"] == -32700
        assert "id" in frames[0], "JSON-RPC requires the id member to be present"
        assert frames[0]["id"] is None

    def test_parse_error_omits_detail_unless_debugging(
        self, monkeypatch: pytest.MonkeyPatch, empty_store: dict[str, Any]
    ) -> None:
        monkeypatch.delenv("MCP_DEBUG_ERRORS", raising=False)
        frames = drive(monkeypatch, "{not json at all")
        assert "data" not in frames[0]["error"]

    def test_loop_survives_and_continues_after_parse_error(
        self, monkeypatch: pytest.MonkeyPatch, empty_store: dict[str, Any]
    ) -> None:
        frames = drive(
            monkeypatch,
            "{broken",
            json.dumps({"jsonrpc": "2.0", "id": 7, "method": "tools/list"}),
        )
        assert frames[0]["error"]["code"] == -32700
        assert frames[1]["id"] == 7 and len(frames[1]["result"]["tools"]) == 8

    def test_notification_receives_no_response(
        self, monkeypatch: pytest.MonkeyPatch, empty_store: dict[str, Any]
    ) -> None:
        frames = drive(
            monkeypatch,
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/list"}),
        )
        assert len(frames) == 1 and frames[0]["id"] == 3


# ---------------------------------------------------------------------------
# BUG-008 — no dead CLI options
# ---------------------------------------------------------------------------
class TestCliSurface:
    def test_mcp_command_takes_no_dead_options(self) -> None:
        import inspect
        from backend.cli import mcp as mcp_command

        assert list(inspect.signature(mcp_command).parameters) == []

    def test_mcp_command_launches_the_stdio_server(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        launched: list[bool] = []
        monkeypatch.setattr(
            "backend.mcp_server.run_mcp_server", lambda: launched.append(True)
        )
        from backend.cli import mcp as mcp_command

        mcp_command()
        assert launched == [True]

    def test_legacy_flag_is_rejected(self) -> None:
        """The removed option must not silently succeed."""
        from typer.testing import CliRunner
        from backend.cli import app

        result = CliRunner().invoke(app, ["mcp", "--legacy"])
        assert result.exit_code != 0
