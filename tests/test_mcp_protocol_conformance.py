"""Regression guard for the stdio MCP server's JSON-RPC conformance.

Drives `scripts/mcp_validate.py` end-to-end against `python -m backend.cli mcp`
and asserts the invariants that must hold regardless of whether any repository
is indexed on the machine running the suite.

Slow tools are skipped so this stays CI-friendly. For the full matrix run:
    python scripts/mcp_validate.py --json report.json
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "mcp_validate.py"


@pytest.fixture(scope="module")
def report(tmp_path_factory: pytest.TempPathFactory) -> dict:
    import os

    out = tmp_path_factory.mktemp("mcp") / "report.json"
    env = dict(
        os.environ,
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        NUMEXPR_NUM_THREADS="1",
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--skip-slow",
            "--timeout",
            "60.0",
            "--json",
            str(out),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert out.exists(), (
        f"validator produced no report.\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    return json.loads(out.read_text(encoding="utf-8"))


def failures(report: dict, phase: str) -> list[str]:
    return [
        f"{r['check']}: {r['note']}"
        for r in report["results"]
        if r["phase"] == phase and r["status"] == "FAIL"
    ]


def find(report: dict, check: str) -> dict:
    matches = [r for r in report["results"] if r["check"] == check]
    assert matches, f"validator never ran the {check!r} check"
    return matches[0]


def test_handshake_is_conformant(report: dict) -> None:
    """initialize must return protocolVersion, capabilities.tools and serverInfo."""
    assert not failures(report, "handshake"), failures(report, "handshake")


def test_tool_discovery_and_schemas(report: dict) -> None:
    """All 8 tools must advertise valid, self-consistent JSON Schemas."""
    assert not failures(report, "discovery"), failures(report, "discovery")
    assert find(report, "tool count")["note"].startswith("8 ")


def test_server_survives_protocol_abuse(report: dict) -> None:
    """Malformed JSON, unknown methods and bad argument types must not kill the loop."""
    assert find(report, "recovered after abuse")["status"] == "PASS"
    assert find(report, "unknown method -> -32601")["status"] == "PASS"
    assert find(report, "malformed JSON -> parse error")["status"] == "PASS"
    assert not any(
        r["check"] == "server alive" and r["status"] == "FAIL"
        for r in report["results"]
    )


def test_stdout_is_reserved_for_jsonrpc(report: dict) -> None:
    """Any non-JSON byte on stdout corrupts the transport for every client."""
    assert find(report, "stdout carries only JSON")["status"] == "PASS"


def test_graceful_shutdown_on_stdin_eof(report: dict) -> None:
    assert find(report, "graceful exit on EOF")["status"] == "PASS"


def test_errors_do_not_leak_tracebacks(report: dict) -> None:
    """Fixed in MCP Stability v1.0 (BUG-002); guards against reintroduction."""
    assert find(report, "no traceback in responses")["status"] == "PASS"
    # Broader sweep: stack traces, source lines and absolute paths in any
    # client-visible failure payload, not just the JSON-RPC error member.
    assert find(report, "no internals in failure payloads")["status"] == "PASS"


def test_no_tool_call_fails_the_protocol_envelope(report: dict) -> None:
    """Every tools/call variant, valid or hostile, must return a conformant frame."""
    assert not failures(report, "tools"), failures(report, "tools")


@pytest.mark.skipif(
    not (ROOT / "data" / "analysis_store.json").exists(),
    reason="no persisted analysis store on this machine",
)
def test_repository_scoped_tools_see_persisted_repositories(report: dict) -> None:
    """A store persisted on disk must be visible to list_repositories over MCP."""
    assert "store empty" not in find(report, "repo under test")["note"]
