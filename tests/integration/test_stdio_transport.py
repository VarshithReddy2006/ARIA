# tests/integration/test_stdio_transport.py
"""Integration test for MCP stdio transport.

This test launches the MCP server via the CLI in a subprocess and communicates
using JSON‑RPC over the subprocess' stdin/stdout streams. It validates the
full transport layer without invoking any internal functions directly.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

# Helper to read a newline-delimited JSON‑RPC message from the stream.
def read_message(stream, proc=None) -> dict:
    line = stream.readline()
    if not line:
        err_msg = ""
        if proc and hasattr(proc, "stderr") and proc.stderr:
            try:
                err_msg = proc.stderr.read()
            except Exception:
                pass
        raise RuntimeError(f"Unexpected EOF while reading message. Server stderr: {err_msg}")
    return json.loads(line)

# Helper to write a newline-delimited JSON‑RPC message to the stream.
def write_message(stream, method: str, params: dict | None = None, request_id: int | None = 1):
    payload = {"jsonrpc": "2.0", "method": method}
    if request_id is not None:
        payload["id"] = request_id
    if params is not None:
        payload["params"] = params
    line = json.dumps(payload) + "\n"
    try:
        stream.write(line)
        stream.flush()
    except (OSError, BrokenPipeError):
        pass

@pytest.fixture(scope="module")
def mcp_process():
    """Start the MCP server via the CLI.

    The entry point is defined in pyproject.toml under ``repo-intel``.
    """
    root_dir = Path(__file__).resolve().parents[2]
    env = dict(
        os.environ,
        PYTHONUNBUFFERED="1",
        PYTHONIOENCODING="utf-8",
        PYTHONPATH=str(root_dir),
    )
    cmd = [sys.executable, "-u", "-m", "backend.cli", "mcp"]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=root_dir,
        env=env,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )
    time.sleep(0.2)
    yield proc
    # Graceful shutdown via JSON‑RPC "shutdown" request if still alive.
    if proc.poll() is None:
        try:
            write_message(proc.stdin, "shutdown", request_id=999)
            proc.wait(timeout=2)
        except Exception:
            proc.kill()
    else:
        proc.kill()

def test_stdio_transport(mcp_process):
    proc = mcp_process
    assert proc.stdin and proc.stdout

    # 1. initialize
    start = time.time()
    write_message(proc.stdin, "initialize", {"processId": None, "rootUri": None, "capabilities": {}})
    init_resp = read_message(proc.stdout, proc)
    latency_initialize = time.time() - start
    assert init_resp.get("id") == 1
    assert init_resp.get("result") is not None

    # 2. initialized notification (no response expected)
    write_message(proc.stdin, "notifications/initialized", None, request_id=None)
    # No response, just ensure server does not error.

    # 3. tools/list request
    start = time.time()
    write_message(proc.stdin, "tools/list", {}, request_id=3)
    tools_resp = read_message(proc.stdout, proc)
    latency_tools = time.time() - start
    tools_result = tools_resp.get("result")
    assert tools_result is not None
    if isinstance(tools_result, dict):
        assert "tools" in tools_result or isinstance(tools_result.get("tools"), list)

    # 4. successful tool execution ("list_repositories")
    start = time.time()
    params = {"name": "list_repositories", "arguments": {}}
    write_message(proc.stdin, "tools/call", params, request_id=4)
    tool_resp = read_message(proc.stdout, proc)
    latency_tool = time.time() - start
    assert tool_resp.get("result") is not None

    # 5. invalid request (unknown tool)
    write_message(proc.stdin, "tools/call", {"name": "nonexistent", "arguments": {}}, request_id=5)
    err_resp = read_message(proc.stdout, proc)
    assert err_resp.get("error") is not None or err_resp.get("result", {}).get("isError") is True

    # 6. graceful shutdown
    write_message(proc.stdin, "shutdown", None, request_id=6)
    shutdown_resp = read_message(proc.stdout, proc)
    assert shutdown_resp.get("id") == 6
    proc.wait(timeout=5)

    # Record latencies (logged for reference, not asserted)
    print(
        f"latencies: initialize={latency_initialize:.3f}s, tools/list={latency_tools:.3f}s, tool=call={latency_tool:.3f}s"
    )
