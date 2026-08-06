#!/usr/bin/env python
"""Protocol conformance validator for the Repo Intelligence stdio MCP server.

Launches `python -m backend.cli mcp` as a subprocess and drives it over raw
stdio JSON-RPC. Validates the handshake, tool discovery, tool execution, and
the negative paths that an SDK-based client (e.g. MCP Inspector) cannot emit.

Read-only: never mutates the repository or production code.

Usage:
    python scripts/mcp_validate.py                # full run
    python scripts/mcp_validate.py --skip-slow    # skip LLM/network-bound tools
    python scripts/mcp_validate.py --json report.json
Exit code: 0 = no FAILs, 1 = at least one FAIL.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
from typing import Any

PROTOCOL_VERSION = "2024-11-05"
SLOW_TOOLS = {
    "get_dead_code",  # builds dependency + call graphs
    "query_codebase",  # LLM round trip
    "get_workspace",  # aggregates every workspace panel (FastMCP only)
    "generate_report",  # composes every analysis (FastMCP only)
    "export_report",  # composes then renders (FastMCP only)
    "analyze_repository",  # clones over the network (FastMCP only)
    "get_impact_analysis",  # LLM-assisted prediction (FastMCP only)
    "semantic_search",  # loads the embedding model (FastMCP only)
}
TRACEBACK_MARKER = "Traceback (most recent call last)"
RESULTS: list[dict[str, Any]] = []
# Every client-visible failure payload (JSON-RPC error objects and isError
# results), collected so the hygiene phase can sweep them for leaked internals.
FAILURE_PAYLOADS: list[str] = []


def record(
    phase: str, name: str, status: str, note: str = "", ms: float | None = None
) -> None:
    RESULTS.append(
        {"phase": phase, "check": name, "status": status, "note": note, "ms": ms}
    )
    icon = {"PASS": "[PASS]", "FAIL": "[FAIL]", "WARN": "[WARN]", "INFO": "[INFO]"}[
        status
    ]
    timing = f" {ms:7.1f}ms" if ms is not None else " " * 10
    print(
        f"{icon}{timing}  {phase:<12} {name}{f' - {note}' if note else ''}", flush=True
    )


class StdioClient:
    """Minimal framed JSON-RPC client over a subprocess' stdin/stdout."""

    def __init__(self, cmd: list[str], cwd: str) -> None:
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        self.stdout_q: queue.Queue[str | None] = queue.Queue()
        self.stderr_lines: list[str] = []
        self.raw_stdout: list[str] = []
        self.stale_frames = 0
        self._id = 0
        t0 = time.perf_counter()
        self.proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self.spawn_ms = (time.perf_counter() - t0) * 1000
        threading.Thread(target=self._pump_stdout, daemon=True).start()
        threading.Thread(target=self._pump_stderr, daemon=True).start()

    def _pump_stdout(self) -> None:
        for line in self.proc.stdout:  # type: ignore[union-attr]
            if line.strip():
                self.raw_stdout.append(line.rstrip("\n"))
                self.stdout_q.put(line.rstrip("\n"))
        self.stdout_q.put(None)

    def _pump_stderr(self) -> None:
        for line in self.proc.stderr:  # type: ignore[union-attr]
            self.stderr_lines.append(line.rstrip("\n"))

    def write_raw(self, payload: str) -> None:
        self.proc.stdin.write(payload + "\n")  # type: ignore[union-attr]
        self.proc.stdin.flush()  # type: ignore[union-attr]

    def read_frame(self, timeout: float) -> tuple[Any, str | None]:
        """Return (parsed_frame, error_reason). None frame means timeout/EOF."""
        try:
            line = self.stdout_q.get(timeout=timeout)
        except queue.Empty:
            return None, f"no response within {timeout}s"
        if line is None:
            return None, "stdout closed (server exited)"
        try:
            return json.loads(line), None
        except json.JSONDecodeError as exc:
            return None, f"non-JSON on stdout ({exc}): {line[:120]!r}"

    def call(
        self, method: str, params: Any = None, timeout: float = 30.0
    ) -> tuple[Any, str | None, float]:
        self._id += 1
        req: dict[str, Any] = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            req["params"] = params
        t0 = time.perf_counter()
        self.write_raw(json.dumps(req))
        # Match on id and discard stale frames. A response that arrives after a
        # previous call timed out would otherwise desynchronise every later
        # check, reporting one slow tool as a dozen protocol failures.
        while True:
            frame, err = self.read_frame(timeout)
            elapsed = (time.perf_counter() - t0) * 1000
            if frame is None or frame.get("id") == self._id:
                return frame, err, elapsed
            if isinstance(frame.get("id"), int) and frame["id"] < self._id:
                self.stale_frames += 1
                continue
            return frame, f"id mismatch: sent {self._id}, got {frame.get('id')!r}", elapsed

    def notify(self, method: str, params: Any = None) -> None:
        req: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            req["params"] = params
        self.write_raw(json.dumps(req))

    def shutdown(self, timeout: float = 10.0) -> tuple[int | None, str]:
        try:
            self.proc.stdin.close()  # type: ignore[union-attr]
        except Exception:
            pass
        try:
            return self.proc.wait(timeout=timeout), "exited on stdin EOF"
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)
            return None, f"did not exit within {timeout}s of EOF; killed"


def check_frame(
    phase: str,
    name: str,
    frame: Any,
    err: str | None,
    ms: float,
    expect_error_code: int | None = None,
) -> bool:
    """Validate envelope shape. Returns True if a usable frame came back."""
    if err or frame is None:
        record(phase, name, "FAIL", err or "no frame", ms)
        return False
    problems = []
    if frame.get("jsonrpc") != "2.0":
        problems.append(f"jsonrpc={frame.get('jsonrpc')!r}")
    if ("result" in frame) == ("error" in frame):
        problems.append("must carry exactly one of result/error")
    if "id" not in frame:
        problems.append("missing 'id' member")
    payload = "error" if "error" in frame else "result"
    detail = "result ok"
    if payload == "error":
        e = frame["error"]
        FAILURE_PAYLOADS.append(json.dumps(e))
        if not isinstance(e.get("code"), int) or not isinstance(e.get("message"), str):
            problems.append("malformed error object")
        if TRACEBACK_MARKER in json.dumps(e):
            problems.append("LEAKS TRACEBACK in error payload")
        if expect_error_code is not None and e.get("code") != expect_error_code:
            problems.append(f"expected code {expect_error_code}, got {e.get('code')}")
        detail = f"error {e.get('code')}: {str(e.get('message'))[:70]}"
    else:
        r = frame["result"]
        # MCP tool failures arrive as a successful result carrying isError.
        if isinstance(r, dict) and r.get("isError"):
            text = " ".join(
                c.get("text", "") for c in r.get("content", []) if isinstance(c, dict)
            )
            FAILURE_PAYLOADS.append(text)
            if TRACEBACK_MARKER in text:
                problems.append("LEAKS TRACEBACK in isError content")
            detail = f"isError: {text.splitlines()[0][:70] if text else '(no message)'}"
        elif expect_error_code is not None:
            problems.append(
                f"expected JSON-RPC error {expect_error_code}, got a result"
            )
    if problems:
        record(phase, name, "FAIL", "; ".join(problems), ms)
        return True
    record(phase, name, "PASS", detail, ms)
    return True


def happy_args(
    tool: str, owner: str, repo: str, file_path: str, symbol: str
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    props = {
        "owner": owner,
        "repo": repo,
        "file_path": file_path,
        "symbol_name": symbol,
        "query": "What does this project do?",
    }
    for key, val in props.items():
        if key in TOOL_SCHEMAS.get(tool, {}).get("properties", {}):
            args[key] = val
    return args


TOOL_SCHEMAS: dict[str, dict[str, Any]] = {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--python", default=sys.executable, help="interpreter that runs the server"
    )
    ap.add_argument("--cwd", default=os.getcwd(), help="project root")
    ap.add_argument(
        "--launch-module",
        default=None,
        help="run 'python -m <module>' instead of 'python -m backend.cli mcp'",
    )
    ap.add_argument(
        "--launch-code",
        default=None,
        help="run 'python -c <code>'; used to drive the FastMCP server, which has "
        "no module entry point of its own",
    )
    ap.add_argument(
        "--expect-tools",
        type=int,
        default=8,
        help="expected tool count (8 for legacy, 17 for FastMCP)",
    )
    ap.add_argument("--owner", default=None)
    ap.add_argument("--repo", default=None)
    ap.add_argument("--file-path", default="backend/mcp_server.py")
    ap.add_argument("--symbol", default="run_mcp_server")
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--slow-timeout", type=float, default=180.0)
    ap.add_argument("--skip-slow", action="store_true")
    ap.add_argument("--json", dest="json_out", default=None)
    a = ap.parse_args()

    if a.launch_code:
        cmd = [a.python, "-c", a.launch_code]
    elif a.launch_module:
        cmd = [a.python, "-m", a.launch_module]
    else:
        cmd = [a.python, "-m", "backend.cli", "mcp"]
    print(f"Server : {' '.join(cmd)}\nCwd    : {a.cwd}\n" + "-" * 88, flush=True)
    c = StdioClient(cmd, a.cwd)
    record("startup", "process spawned", "INFO", f"pid {c.proc.pid}", c.spawn_ms)

    # ---- Phase 1: handshake -------------------------------------------------
    frame, err, ms = c.call(
        "initialize",
        {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "mcp-validate", "version": "1.0.0"},
        },
        a.timeout,
    )
    if not check_frame("handshake", "initialize", frame, err, ms):
        record(
            "handshake",
            "server reachable",
            "FAIL",
            "aborting; stderr tail: " + " | ".join(c.stderr_lines[-3:]),
        )
        return finish(c, a.json_out)
    res = (frame or {}).get("result", {})
    record(
        "handshake",
        "protocolVersion",
        "PASS" if res.get("protocolVersion") else "FAIL",
        str(res.get("protocolVersion")),
    )
    caps = res.get("capabilities", {})
    record(
        "handshake",
        "capabilities.tools",
        "PASS" if "tools" in caps else "FAIL",
        json.dumps(caps),
    )
    info = res.get("serverInfo", {})
    record(
        "handshake",
        "serverInfo",
        "PASS" if info.get("name") and info.get("version") else "FAIL",
        f"{info.get('name')} v{info.get('version')}",
    )

    # initialized notification must NOT produce a response
    c.notify("notifications/initialized")
    frame, err, ms = c.call("tools/list", {}, a.timeout)
    if frame is not None and frame.get("id") == 2:
        record(
            "handshake",
            "initialized notification silent",
            "PASS",
            "no reply to notification",
        )
    else:
        record(
            "handshake",
            "initialized notification silent",
            "FAIL",
            "server replied to a notification",
        )

    # ---- Phase 2: discovery -------------------------------------------------
    check_frame("discovery", "tools/list", frame, err, ms)
    tools = ((frame or {}).get("result") or {}).get("tools") or []
    record(
        "discovery",
        "tool count",
        "PASS" if len(tools) == a.expect_tools else "WARN",
        f"{len(tools)} tools (expected {a.expect_tools})",
    )
    for t in tools:
        name = t.get("name", "<unnamed>")
        schema = t.get("inputSchema") or {}
        TOOL_SCHEMAS[name] = schema
        issues = []
        if not t.get("description"):
            issues.append("no description")
        if schema.get("type") != "object":
            issues.append(f"inputSchema.type={schema.get('type')!r}")
        if not isinstance(schema.get("properties"), dict):
            issues.append("properties not an object")
        for req in schema.get("required", []):
            if req not in schema.get("properties", {}):
                issues.append(f"required '{req}' absent from properties")
        req_list = ",".join(schema.get("required", [])) or "none"
        record(
            "discovery",
            f"schema {name}",
            "FAIL" if issues else "PASS",
            "; ".join(issues) or f"required: {req_list}",
        )

    # ---- Phase 3: resolve a live repository --------------------------------
    owner, repo = a.owner, a.repo
    if not (owner and repo):
        frame, err, ms = c.call(
            "tools/call", {"name": "list_repositories", "arguments": {}}, a.timeout
        )
        check_frame("fixture", "list_repositories", frame, err, ms)
        try:
            listed = json.loads((frame or {})["result"]["content"][0]["text"])
        except Exception:
            listed = []
        if listed:
            owner, _, repo = str(listed[0]).partition("/")
            record(
                "fixture",
                "repo under test",
                "INFO",
                f"{owner}/{repo} (of {len(listed)} indexed)",
            )
        else:
            owner, repo = "octocat", "Spoon-Knife"
            record(
                "fixture",
                "repo under test",
                "WARN",
                "store empty; happy paths will exercise error paths",
            )

    # ---- Phase 4: per-tool matrix ------------------------------------------
    for name in [t.get("name") for t in tools]:
        if not name:
            continue
        tmo = a.slow_timeout if name in SLOW_TOOLS else a.timeout
        if a.skip_slow and name in SLOW_TOOLS:
            record("tools", f"{name}", "WARN", "skipped via --skip-slow")
            continue
        variants: list[tuple[str, Any]] = [
            ("A happy", happy_args(name, owner, repo, a.file_path, a.symbol)),
            (
                "B bad repo",
                happy_args(
                    name, "zz-no-such-owner", "zz-no-such-repo", a.file_path, a.symbol
                ),
            ),
            ("C missing req", {}),
            (
                "D bad types",
                {
                    k: 12345
                    for k in happy_args(name, owner, repo, a.file_path, a.symbol)
                },
            ),
            (
                "E odd values",
                {
                    **happy_args(name, "", "", "", ""),
                    "__unexpected__": [None, {"x": 1}],
                },
            ),
        ]
        for label, args in variants:
            frame, err, ms = c.call(
                "tools/call", {"name": name, "arguments": args}, tmo
            )
            check_frame("tools", f"{name} :: {label}", frame, err, ms)
            if c.proc.poll() is not None:
                record(
                    "tools",
                    "server alive",
                    "FAIL",
                    f"process died during {name} {label}",
                )
                return finish(c, a.json_out)

    # ---- Phase 5: protocol abuse -------------------------------------------
    frame, err, ms = c.call(
        "tools/call", {"name": "no_such_tool_xyz", "arguments": {}}, a.timeout
    )
    check_frame("abuse", "unknown tool name", frame, err, ms)
    frame, err, ms = c.call("definitely/not/a/method", {}, a.timeout)
    check_frame(
        "abuse", "unknown method -> -32601", frame, err, ms, expect_error_code=-32601
    )

    t0 = time.perf_counter()
    c.write_raw('{"jsonrpc":"2.0","id":999,"method":"tools/list"')  # truncated JSON
    frame, err = c.read_frame(a.timeout)
    ms = (time.perf_counter() - t0) * 1000
    if frame is None:
        record("abuse", "malformed JSON -> parse error", "FAIL", err or "no reply", ms)
    else:
        code = (frame.get("error") or {}).get("code")
        note = f"code {code}" + (
            "" if "id" in frame else "; MISSING 'id' member (JSON-RPC requires id:null)"
        )
        record(
            "abuse",
            "malformed JSON -> parse error",
            "PASS" if code == -32700 else "FAIL",
            note,
            ms,
        )

    frame, err, ms = c.call(
        "tools/call",
        {"name": "list_repositories", "arguments": "not-an-object"},
        a.timeout,
    )
    check_frame("abuse", "arguments not an object", frame, err, ms)
    frame, err, ms = c.call("tools/list", {}, a.timeout)
    record(
        "abuse",
        "recovered after abuse",
        "PASS" if frame and "result" in frame else "FAIL",
        "still serving requests",
        ms,
    )

    return finish(c, a.json_out)


def finish(c: StdioClient, json_out: str | None) -> int:
    code, note = c.shutdown()
    record(
        "shutdown",
        "graceful exit on EOF",
        "PASS" if code == 0 else "FAIL",
        f"rc={code}; {note}",
    )

    bad_stdout = [ln for ln in c.raw_stdout if not ln.lstrip().startswith("{")]
    record(
        "hygiene",
        "stdout carries only JSON",
        "PASS" if not bad_stdout else "FAIL",
        "clean"
        if not bad_stdout
        else f"{len(bad_stdout)} stray line(s): {bad_stdout[0][:80]!r}",
    )
    leaks = sum(1 for r in RESULTS if "LEAKS TRACEBACK" in r["note"])
    record(
        "hygiene",
        "no traceback in responses",
        "PASS" if not leaks else "FAIL",
        "clean" if not leaks else f"{leaks} response(s) leaked a stack trace",
    )

    # Sweep every failure payload for internals. Scoped to failures on purpose:
    # successful results legitimately contain repository file paths (e.g.
    # analysis.metadata.local_path), so scanning them would false-positive.
    blob = "\n".join(FAILURE_PAYLOADS)
    internals = {
        "traceback header": TRACEBACK_MARKER,
        "source line": 'File "',
        "drive-letter path": ":\\",
        "site-packages path": "site-packages",
        "interpreter frame": ", line ",
    }
    found = [label for label, needle in internals.items() if needle in blob]
    record(
        "hygiene",
        "no internals in failure payloads",
        "PASS" if not found else "FAIL",
        f"{len(FAILURE_PAYLOADS)} failure payload(s) clean"
        if not found
        else "leaked: " + ", ".join(found),
    )
    record(
        "hygiene",
        "response ordering",
        "PASS" if not c.stale_frames else "WARN",
        "in order"
        if not c.stale_frames
        else f"{c.stale_frames} late frame(s) discarded after a timeout",
    )
    tb_stderr = sum(1 for ln in c.stderr_lines if TRACEBACK_MARKER in ln)
    record(
        "hygiene",
        "stderr tracebacks",
        "INFO" if tb_stderr else "PASS",
        f"{tb_stderr} on stderr (not client-visible)",
    )

    print("-" * 88)
    timed = [r for r in RESULTS if r["ms"]]
    tally = {
        s: sum(1 for r in RESULTS if r["status"] == s)
        for s in ("PASS", "FAIL", "WARN", "INFO")
    }
    print(
        f"PASS {tally['PASS']}   FAIL {tally['FAIL']}   WARN {tally['WARN']}   INFO {tally['INFO']}"
    )
    if timed:
        slowest = max(timed, key=lambda r: r["ms"])
        print(
            f"latency: max {slowest['ms']:.0f}ms ({slowest['check']}), "
            f"median {sorted(r['ms'] for r in timed)[len(timed) // 2]:.0f}ms"
        )
    for r in RESULTS:
        if r["status"] == "FAIL":
            print(f"  FAIL  {r['phase']}/{r['check']}: {r['note']}")
    if json_out:
        with open(json_out, "w", encoding="utf-8") as fh:
            json.dump({"results": RESULTS, "stderr": c.stderr_lines}, fh, indent=2)
        print(f"report -> {json_out}")
    return 1 if tally["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
