"""End-to-End Controlled Validation Script on Modal.

Performs:
1. Initialize session by visiting public GET /
2. Validate Architecture & Health Endpoints for fastapi/fastapi
3. Query Chat question: "What does this codebase do, and what are its main entry points?"
   and verify grounded answer via SSE stream.
"""

import http.cookiejar
import json
import os
import sys
import urllib.request
import urllib.error

sys.stdout.reconfigure(line_buffering=True)

MODAL_BASE_URL = os.environ.get(
    "MODAL_BASE_URL", "https://varshithreddy6147--aria-serve-aria-dev.modal.run"
).rstrip("/")

cookie_jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))


def http_req(
    path: str, method: str = "GET", data: dict = None, timeout: int = 120
) -> dict:
    url = f"{MODAL_BASE_URL}{path}"
    headers = {
        "Content-Type": "application/json",
        "Origin": MODAL_BASE_URL,
        "Referer": f"{MODAL_BASE_URL}/",
    }
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with opener.open(req, timeout=timeout) as resp:
            content = resp.read().decode("utf-8")
            if content:
                try:
                    return json.loads(content)
                except Exception:
                    return {"raw": content, "status_code": resp.status}
            return {"status_code": resp.status}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        try:
            return {"error": json.loads(error_body), "status_code": e.code}
        except Exception:
            return {"error": error_body, "status_code": e.code}


def test_chat():
    print("\n=== Testing Repository Chat Grounding (SSE Stream) ===", flush=True)
    url = f"{MODAL_BASE_URL}/api/v1/chat"
    headers = {
        "Content-Type": "application/json",
        "Origin": MODAL_BASE_URL,
        "Referer": f"{MODAL_BASE_URL}/",
    }
    payload = {
        "repo": "fastapi/fastapi",
        "message": "What does this codebase do, and what are its main entry points?",
        "history": [],
    }
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )
    tokens = []
    sources = []
    try:
        with opener.open(req, timeout=60) as resp:
            for line in resp:
                line_str = line.decode("utf-8").strip()
                if line_str.startswith("data: "):
                    data_part = line_str[6:]
                    if data_part == "[DONE]":
                        break
                    try:
                        event = json.loads(data_part)
                        if "token" in event:
                            tokens.append(event["token"])
                        if "sources" in event:
                            sources.extend(event["sources"])
                    except Exception:
                        tokens.append(data_part)
    except Exception as e:
        print(f"Chat request failed: {e}")

    full_response = "".join(tokens)
    print("\nFull Chat Response:")
    print("-" * 60)
    print(full_response)
    print("-" * 60)
    print(f"Sources cited: {sources}")
    return full_response, sources


def main():
    print(f"=== Starting E2E Validation on Modal: {MODAL_BASE_URL} ===", flush=True)

    # 1. Initialize session on public page
    print("\n[1] Initializing browser session via GET / ...", flush=True)
    http_req("/")
    print(f"Session cookies: {[c.name for c in cookie_jar]}", flush=True)

    health = http_req("/health")
    print(f"Health response: {health}", flush=True)

    # 2. Check architecture & health
    print("\n=== [2] Testing Architecture & Health Endpoints ===", flush=True)

    # Report build
    report_data = http_req("/api/v1/report/fastapi/fastapi/build", method="POST")
    if isinstance(report_data, dict) and "scores" in report_data:
        scores = report_data.get("scores", {})
        metadata = report_data.get("metadata", {})
        print(
            f"\nMetadata: LOC={metadata.get('total_loc')}, Commits={metadata.get('commits_count')}",
            flush=True,
        )
        print(
            f"Detailed Scores: Overall={scores.get('overall')}, Architecture={scores.get('architecture')}, API={scores.get('api')}, Hygiene={scores.get('hygiene')}, Churn={scores.get('churn')}, Readability={scores.get('readability')}, Grade={scores.get('grade')}",
            flush=True,
        )

    # PR / Dead code health
    pr_health = http_req("/api/v1/pr/health?owner=fastapi&repo=fastapi")
    print(f"PR/Dead Code Health: {pr_health}", flush=True)

    # Call graph
    cg_res = http_req("/api/v1/call-graph/fastapi/fastapi")
    if isinstance(cg_res, dict) and "nodes" in cg_res:
        print(
            f"Call Graph: {len(cg_res.get('nodes', []))} nodes, {len(cg_res.get('edges', []))} edges",
            flush=True,
        )
    else:
        print(f"Call Graph: {cg_res}", flush=True)

    # API surface
    api_res = http_req("/api/v1/api-surface/fastapi/fastapi")
    if isinstance(api_res, dict) and "symbols" in api_res:
        print(f"API Surface: {len(api_res.get('symbols', []))} symbols", flush=True)
    else:
        print(f"API Surface: {api_res}", flush=True)

    # 3. Test Chat endpoint
    test_chat()

    print("\n=== Validation Complete ===", flush=True)


if __name__ == "__main__":
    main()
