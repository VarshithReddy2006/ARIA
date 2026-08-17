"""Asynchronous SSE Client for load testing ARIA streaming endpoints."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import httpx

DEFAULT_BENCHMARK_KEY = "aria-benchmark-key"


@dataclass
class SSEResult:
    """Result and metrics for a single SSE stream execution."""

    success: bool = False
    status_code: int = 0
    connect_time_ms: float = 0.0
    ttft_ms: Optional[float] = None
    duration_ms: float = 0.0
    tokens_count: int = 0
    events_count: int = 0
    bytes_received: int = 0
    full_text: str = ""
    sources: List[str] = field(default_factory=list)
    confidence: Optional[int] = None
    fallback_mode: bool = False
    status_done: bool = False
    error: Optional[str] = None
    events: List[Dict[str, Any]] = field(default_factory=list)


async def consume_chat_stream(
    client: httpx.AsyncClient,
    base_url: str,
    repo: str,
    message: str,
    session_id: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 60.0,
) -> SSEResult:
    """Consume POST /api/v1/chat SSE stream and compute metrics."""
    result = SSEResult()
    url = f"{base_url.rstrip('/')}/api/v1/chat"
    payload = {
        "repo": repo,
        "message": message,
        "history": [],
    }
    if session_id:
        payload["session_id"] = session_id

    req_headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "X-API-Key": DEFAULT_BENCHMARK_KEY,
    }
    if headers:
        req_headers.update(headers)

    t_start = time.perf_counter()
    try:
        async with client.stream(
            "POST", url, json=payload, headers=req_headers, timeout=timeout
        ) as response:
            result.status_code = response.status_code
            result.connect_time_ms = (time.perf_counter() - t_start) * 1000.0

            if response.status_code != 200:
                body = await response.aread()
                result.error = f"HTTP {response.status_code}: {body.decode('utf-8', errors='ignore')}"
                result.duration_ms = (time.perf_counter() - t_start) * 1000.0
                return result

            buffer = ""
            async for chunk in response.aiter_text():
                result.bytes_received += len(chunk.encode("utf-8"))
                buffer += chunk
                while "\n\n" in buffer:
                    event_str, buffer = buffer.split("\n\n", 1)
                    for line in event_str.split("\n"):
                        line = line.strip()
                        if line.startswith("data:"):
                            raw_json = line[5:].strip()
                            if not raw_json:
                                continue
                            try:
                                data = json.loads(raw_json)
                                result.events.append(data)
                                result.events_count += 1

                                if "text" in data:
                                    token = data["text"]
                                    if result.ttft_ms is None:
                                        result.ttft_ms = (
                                            time.perf_counter() - t_start
                                        ) * 1000.0
                                    result.tokens_count += 1
                                    result.full_text += token

                                if data.get("status") == "done":
                                    result.status_done = True
                                    result.sources = data.get("sources", [])
                                    result.confidence = data.get("confidence")
                                    result.fallback_mode = bool(
                                        data.get("fallback_mode", False)
                                    )

                                if "error" in data:
                                    result.error = data.get("message") or data.get(
                                        "error"
                                    )
                            except json.JSONDecodeError:
                                pass

            result.duration_ms = (time.perf_counter() - t_start) * 1000.0
            if result.status_done and not result.error:
                result.success = True
            elif not result.status_done and not result.error:
                result.error = (
                    "Incomplete stream: stream closed before terminal status=done event"
                )

    except httpx.TimeoutException:
        result.error = f"Request timed out after {timeout}s"
        result.duration_ms = (time.perf_counter() - t_start) * 1000.0
    except Exception as exc:
        result.error = f"Stream failed: {type(exc).__name__}: {exc}"
        result.duration_ms = (time.perf_counter() - t_start) * 1000.0

    return result


async def consume_analyze_stream(
    client: httpx.AsyncClient,
    base_url: str,
    repo_url: str,
    branch: Optional[str] = None,
    force_rebuild: bool = False,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 180.0,
) -> SSEResult:
    """Consume POST /api/v1/analyze SSE stream and compute metrics."""
    result = SSEResult()
    url = f"{base_url.rstrip('/')}/api/v1/analyze"
    payload = {
        "url": repo_url,
        "branch": branch or "main",
        "force_rebuild": force_rebuild,
    }

    req_headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "X-API-Key": DEFAULT_BENCHMARK_KEY,
    }
    if headers:
        req_headers.update(headers)

    t_start = time.perf_counter()
    try:
        async with client.stream(
            "POST", url, json=payload, headers=req_headers, timeout=timeout
        ) as response:
            result.status_code = response.status_code
            result.connect_time_ms = (time.perf_counter() - t_start) * 1000.0

            if response.status_code != 200:
                body = await response.aread()
                result.error = f"HTTP {response.status_code}: {body.decode('utf-8', errors='ignore')}"
                result.duration_ms = (time.perf_counter() - t_start) * 1000.0
                return result

            buffer = ""
            async for chunk in response.aiter_text():
                result.bytes_received += len(chunk.encode("utf-8"))
                buffer += chunk
                while "\n\n" in buffer:
                    event_str, buffer = buffer.split("\n\n", 1)
                    for line in event_str.split("\n"):
                        line = line.strip()
                        if line.startswith("data:"):
                            raw_json = line[5:].strip()
                            if not raw_json:
                                continue
                            try:
                                data = json.loads(raw_json)
                                result.events.append(data)
                                result.events_count += 1

                                if result.ttft_ms is None:
                                    result.ttft_ms = (
                                        time.perf_counter() - t_start
                                    ) * 1000.0

                                if data.get("status") == "done":
                                    result.status_done = True
                                elif data.get("status") == "error":
                                    result.error = data.get("message", "Analysis error")
                            except json.JSONDecodeError:
                                pass

            result.duration_ms = (time.perf_counter() - t_start) * 1000.0
            if result.status_done and not result.error:
                result.success = True
            elif not result.status_done and not result.error:
                result.error = "Incomplete stream: stream closed before status=done"

    except httpx.TimeoutException:
        result.error = f"Analysis timed out after {timeout}s"
        result.duration_ms = (time.perf_counter() - t_start) * 1000.0
    except Exception as exc:
        result.error = f"Analyze stream failed: {type(exc).__name__}: {exc}"
        result.duration_ms = (time.perf_counter() - t_start) * 1000.0

    return result
