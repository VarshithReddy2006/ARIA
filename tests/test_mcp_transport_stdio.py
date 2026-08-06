"""Real stdio transport certification for both MCP servers (v1.5.0).

Every other MCP test drives the servers in-process. These tests launch them as
subprocesses and speak newline-delimited JSON-RPC over real pipes, which is the
only way to catch transport-level faults: event-loop blocking, pipe deadlocks,
buffering bugs, and shutdown hangs.

Two defects were found this way and are locked in here:

* FastMCP executed synchronous tool bodies directly on the asyncio event loop.
  The first ``tools/call`` triggered a lazy numpy/ChromaDB import chain, blocked
  the loop for tens of seconds, and presented as a transport hang.
* FastMCP never hydrated ``ANALYSIS_STORE``, so ``list_repositories`` returned
  ``[]`` on a machine with persisted analyses. Legacy fixed this in v1.0.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Iterator

import pytest

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data" / "analysis_store.json"

LEGACY_CMD = [sys.executable, "-m", "backend.cli", "mcp"]
FASTMCP_CMD = [
    sys.executable, "-u", "-c",
    "from mcp.server import run_mcp_server; run_mcp_server('stdio')",
]

# Generous: a cold start imports the ML/vector stack. Tight enough to catch hangs.
HANDSHAKE_TIMEOUT = 120.0
CALL_TIMEOUT = 60.0


class StdioPeer:
    """Newline-delimited JSON-RPC client over a subprocess' pipes.

    Both pipes are drained by dedicated threads. Without that, a server writing
    more than the OS pipe buffer (~64 KiB) to stderr blocks forever, which is a
    deadlock in the *test*, easily mistaken for a server fault.
    """

    def __init__(self, cmd: list[str]) -> None:
        env = dict(
            os.environ,
            PYTHONUNBUFFERED="1",
            PYTHONIOENCODING="utf-8",
            PYTHONPATH=str(ROOT),
        )
        self.spawned_at = time.perf_counter()
        self.proc = subprocess.Popen(
            cmd, cwd=str(ROOT), env=env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", bufsize=1,
        )
        self.spawn_ms = (time.perf_counter() - self.spawned_at) * 1000
        self._frames: queue.Queue[str | None] = queue.Queue()
        self.stderr: list[str] = []
        self.stdout_raw: list[str] = []
        self.unsolicited: list[dict[str, Any]] = []
        threading.Thread(target=self._pump_out, daemon=True).start()
        threading.Thread(target=self._pump_err, daemon=True).start()
        self._id = 0

    def _pump_out(self) -> None:
        for line in self.proc.stdout:  # type: ignore[union-attr]
            if line.strip():
                self.stdout_raw.append(line.rstrip("\n"))
                self._frames.put(line.rstrip("\n"))
        self._frames.put(None)

    def _pump_err(self) -> None:
        for line in self.proc.stderr:  # type: ignore[union-attr]
            self.stderr.append(line.rstrip("\n"))

    def send_raw(self, payload: str) -> None:
        if self.proc.poll() is not None:
            return
        stdin = self.proc.stdin
        if stdin is not None:
            try:
                if hasattr(stdin, "buffer") and stdin.buffer is not None:
                    stdin.buffer.write(payload.encode("utf-8") + b"\n")
                    stdin.buffer.flush()
                else:
                    stdin.write(payload + "\n")
                    stdin.flush()
            except (OSError, BrokenPipeError):
                pass

    def notify(self, method: str) -> None:
        self.send_raw(json.dumps({"jsonrpc": "2.0", "method": method}))

    def next_frame(self, timeout: float) -> dict[str, Any] | None:
        try:
            line = self._frames.get(timeout=timeout)
        except queue.Empty:
            return None
        return None if line is None else json.loads(line)

    def request(
        self, method: str, params: Any = None, timeout: float = CALL_TIMEOUT
    ) -> tuple[dict[str, Any] | None, float]:
        self._id += 1
        req: dict[str, Any] = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            req["params"] = params
        started = time.perf_counter()
        self.send_raw(json.dumps(req))
        while True:
            frame = self.next_frame(timeout)
            elapsed = (time.perf_counter() - started) * 1000
            if frame is None:
                return None, elapsed
            if frame.get("id") == self._id:
                return frame, elapsed
            # Skip frames that are not answers to this request: server-initiated
            # notifications (no id), and parse errors, which JSON-RPC requires to
            # carry id:null because the offending id could not be recovered.
            if frame.get("id") is None:
                self.unsolicited.append(frame)
                continue
            return frame, elapsed

    def handshake(self) -> tuple[dict[str, Any] | None, float]:
        frame, ms = self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "v1.5.0-transport", "version": "1.5.0"},
            },
            timeout=HANDSHAKE_TIMEOUT,
        )
        self.notify("notifications/initialized")
        return frame, ms

    def shutdown(self, timeout: float = 20.0) -> tuple[int | None, float]:
        started = time.perf_counter()
        try:
            self.proc.stdin.close()  # type: ignore[union-attr]
        except Exception:
            pass
        try:
            code = self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)
            code = None
        return code, (time.perf_counter() - started) * 1000


def peer(cmd: list[str]) -> Iterator[StdioPeer]:
    client = StdioPeer(cmd)
    try:
        yield client
    finally:
        if client.proc.poll() is None:
            client.proc.kill()
            client.proc.wait(timeout=10)


@pytest.fixture(scope="module")
def legacy() -> Iterator[StdioPeer]:
    yield from peer(LEGACY_CMD)


@pytest.fixture(scope="module")
def fastmcp() -> Iterator[StdioPeer]:
    pytest.importorskip("anyio")
    from mcp.server import FastMCP

    if FastMCP is None:
        pytest.skip("mcp SDK not installed; FastMCP transport cannot start")
    yield from peer(FASTMCP_CMD)


# ---------------------------------------------------------------------------
# Shared protocol expectations, run against both servers
# ---------------------------------------------------------------------------
class TransportContract:
    """Assertions every MCP server must satisfy over real stdio."""

    expected_min_tools: int

    def test_initialize(self, client: StdioPeer) -> None:
        frame, ms = client.handshake()
        assert frame is not None, f"no initialize response; stderr: {client.stderr[-5:]}"
        result = frame["result"]
        assert result["protocolVersion"]
        assert "tools" in result["capabilities"]
        assert result["serverInfo"]["name"]
        assert ms < HANDSHAKE_TIMEOUT * 1000

    def test_tools_list(self, client: StdioPeer) -> None:
        frame, _ = client.request("tools/list", {})
        assert frame is not None, "no tools/list response"
        tools = frame["result"]["tools"]
        assert len(tools) >= self.expected_min_tools
        for tool in tools:
            assert tool["name"]
            assert tool["inputSchema"]["type"] == "object"

    def test_tool_execution_does_not_block_the_transport(
        self, client: StdioPeer
    ) -> None:
        """list_repositories must answer promptly and the server stay responsive.

        This is the regression lock for the event-loop blocking defect: the first
        tools/call used to stall for tens of seconds behind a lazy import.
        """
        frame, ms = client.request(
            "tools/call", {"name": "list_repositories", "arguments": {}}
        )
        assert frame is not None, "tools/call did not answer: transport stalled"
        assert ms < CALL_TIMEOUT * 1000
        # Still alive afterwards.
        follow_up, _ = client.request("tools/list", {})
        assert follow_up is not None

    def test_persisted_repositories_are_visible(self, client: StdioPeer) -> None:
        """Regression lock: the store must be hydrated before serving tools."""
        if not STORE.exists():
            pytest.skip("no persisted analysis store on this machine")
        frame, _ = client.request(
            "tools/call", {"name": "list_repositories", "arguments": {}}
        )
        assert frame is not None
        listed = json.loads(frame["result"]["content"][0]["text"])
        assert listed, "server reported no repositories despite a persisted store"

    def test_invalid_parameters_are_rejected(self, client: StdioPeer) -> None:
        frame, _ = client.request(
            "tools/call",
            {"name": "get_call_graph", "arguments": {"owner": "", "repo": "x"}},
        )
        assert frame is not None, "no response to invalid parameters"
        blob = json.dumps(frame)
        assert "error" in frame or frame["result"].get("isError"), blob
        assert "Traceback (most recent call last)" not in blob

    def test_malformed_json_does_not_kill_the_server(self, client: StdioPeer) -> None:
        """The framing error may or may not draw a reply, but must not be fatal.

        Legacy answers -32700 with id:null. The SDK instead logs an error
        notification and sends no reply. Both are survivable; the contract that
        matters here is that the next request still works.
        """
        client.send_raw('{"jsonrpc":"2.0","id":4242,"method":"tools/list"')
        frame, _ = client.request("tools/list", {}, timeout=30.0)
        assert frame is not None, "server stopped serving after malformed JSON"
        assert frame["result"]["tools"]

    def test_stdout_carries_only_json(self, client: StdioPeer) -> None:
        stray = [ln for ln in client.stdout_raw if not ln.lstrip().startswith("{")]
        assert not stray, f"non-JSON on stdout corrupts the stream: {stray[:2]}"

    # Shutdown is deliberately not part of this shared contract: closing stdin
    # ends the module-scoped process and would break every later test. It is
    # covered below against a dedicated, freshly spawned server.


class TestLegacyStdioTransport(TransportContract):
    expected_min_tools = 8

    @pytest.fixture
    def client(self, legacy: StdioPeer) -> StdioPeer:
        return legacy

    def test_parse_error_is_jsonrpc_compliant(self, legacy: StdioPeer) -> None:
        """Legacy answers malformed JSON with -32700 and an explicit null id."""
        legacy.send_raw('{"jsonrpc":"2.0","id":7,"method":"tools/list"')
        frame = legacy.next_frame(timeout=30.0)
        assert frame is not None
        assert frame["error"]["code"] == -32700
        assert "id" in frame and frame["id"] is None


class TestFastMCPStdioTransport(TransportContract):
    expected_min_tools = 17

    @pytest.fixture
    def client(self, fastmcp: StdioPeer) -> StdioPeer:
        return fastmcp

    def test_business_failure_sets_is_error(self, fastmcp: StdioPeer) -> None:
        """The client-visible proof of MCP-compliant tool errors."""
        frame, _ = fastmcp.request(
            "tools/call",
            {"name": "get_call_graph", "arguments": {"owner": "zz", "repo": "zz"}},
        )
        assert frame is not None
        assert frame["result"]["isError"] is True
        text = " ".join(
            c.get("text", "") for c in frame["result"].get("content", [])
        )
        assert "No call graph indexed" in text
        assert "Traceback (most recent call last)" not in text
        assert ":\\" not in text, "leaked a filesystem path"

    def test_successful_call_clears_is_error(self, fastmcp: StdioPeer) -> None:
        frame, _ = fastmcp.request(
            "tools/call", {"name": "list_repositories", "arguments": {}}
        )
        assert frame is not None
        assert frame["result"].get("isError") is False


# ---------------------------------------------------------------------------
# Lifecycle: each case owns its own process
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("label", ["legacy", "fastmcp"])
def test_graceful_shutdown_on_stdin_eof(label: str) -> None:
    """Closing stdin must end the process cleanly, with no hang and rc=0."""
    if label == "fastmcp":
        from mcp.server import FastMCP

        if FastMCP is None:
            pytest.skip("mcp SDK not installed")
    client = StdioPeer(LEGACY_CMD if label == "legacy" else FASTMCP_CMD)
    try:
        frame, _ = client.handshake()
        assert frame is not None, f"{label} never completed initialize"
    finally:
        code, ms = client.shutdown()
    assert code == 0, f"{label} exited {code} after {ms:.0f}ms (expected 0)"
    assert ms < 20_000, f"{label} took {ms:.0f}ms to exit"


@pytest.mark.parametrize("label", ["legacy", "fastmcp"])
def test_startup_and_handshake_latency_is_recorded(
    label: str, record_property: Any
) -> None:
    """Publish transport latencies so regressions are visible in CI output."""
    if label == "fastmcp":
        from mcp.server import FastMCP

        if FastMCP is None:
            pytest.skip("mcp SDK not installed")
    client = StdioPeer(LEGACY_CMD if label == "legacy" else FASTMCP_CMD)
    try:
        frame, handshake_ms = client.handshake()
        assert frame is not None
        _, list_ms = client.request("tools/list", {})
        _, call_ms = client.request(
            "tools/call", {"name": "list_repositories", "arguments": {}}
        )
    finally:
        _, shutdown_ms = client.shutdown()

    record_property(f"{label}_spawn_ms", round(client.spawn_ms, 1))
    record_property(f"{label}_initialize_ms", round(handshake_ms, 1))
    record_property(f"{label}_tools_list_ms", round(list_ms, 1))
    record_property(f"{label}_first_tool_ms", round(call_ms, 1))
    record_property(f"{label}_shutdown_ms", round(shutdown_ms, 1))

    # Guard rails rather than benchmarks: these catch a stall, not a slow laptop.
    assert handshake_ms < HANDSHAKE_TIMEOUT * 1000
    assert list_ms < 30_000
    assert call_ms < CALL_TIMEOUT * 1000
