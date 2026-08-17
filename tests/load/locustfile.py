"""Locust Load Testing Suite for ARIA.

Execute with:
  locust -f tests/load/locustfile.py --headless -u 25 -r 5 --run-time 1m --host http://127.0.0.1:8001
"""

from __future__ import annotations

import json
import random
from locust import HttpUser, task, between
from tests.load.scenarios import (
    BENCHMARK_REPO,
    REALISTIC_CHAT_QUERIES,
    BROWSING_ENDPOINTS,
    LIGHTWEIGHT_ENDPOINTS,
)


class AriaUser(HttpUser):
    """Simulates a realistic developer interacting with ARIA."""

    wait_time = between(1.0, 3.0)

    @task(6)
    def chat_sse(self):
        """Scenario A: Chat SSE streaming."""
        question = random.choice(REALISTIC_CHAT_QUERIES)
        payload = {
            "repo": BENCHMARK_REPO,
            "message": question,
            "history": [],
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

        with self.client.post(
            "/api/v1/chat",
            json=payload,
            headers=headers,
            stream=True,
            catch_response=True,
            name="/api/v1/chat [SSE]",
            timeout=60.0,
        ) as response:
            if response.status_code != 200:
                response.failure(f"Status code: {response.status_code}")
                return

            tokens_received = 0
            has_done = False
            try:
                for line in response.iter_lines():
                    if not line:
                        continue
                    line_str = line.decode("utf-8") if isinstance(line, bytes) else line
                    if line_str.startswith("data:"):
                        data_str = line_str[5:].strip()
                        if data_str:
                            try:
                                data = json.loads(data_str)
                                if "text" in data:
                                    tokens_received += 1
                                if data.get("status") == "done":
                                    has_done = True
                            except Exception:
                                pass
                if has_done:
                    response.success()
                else:
                    response.failure("SSE stream ended without status=done")
            except Exception as e:
                response.failure(f"SSE stream error: {e}")

    @task(2)
    def repo_analysis(self):
        """Scenario B: Trigger and monitor repository analysis."""
        payload = {
            "url": f"https://github.com/{BENCHMARK_REPO}",
            "branch": "main",
            "force_rebuild": False,
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        with self.client.post(
            "/api/v1/analyze",
            json=payload,
            headers=headers,
            stream=True,
            catch_response=True,
            name="/api/v1/analyze [SSE]",
            timeout=120.0,
        ) as response:
            if response.status_code != 200:
                response.failure(f"Status code: {response.status_code}")
                return
            has_done = False
            for line in response.iter_lines():
                if not line:
                    continue
                line_str = line.decode("utf-8") if isinstance(line, bytes) else line
                if line_str.startswith("data:") and '"status": "done"' in line_str:
                    has_done = True
            if has_done:
                response.success()
            else:
                response.failure("Analysis stream missing done status")

    @task(1)
    def repo_browsing(self):
        """Scenario C1: Repository browsing and intelligence endpoints."""
        ep = random.choice(BROWSING_ENDPOINTS)
        self.client.request(
            method=ep["method"],
            url=ep["path"],
            name=f"Browsing: {ep['path'].split('?')[0]}",
            timeout=15.0,
        )

    @task(1)
    def lightweight_ops(self):
        """Scenario C2: Health and metrics telemetry."""
        ep = random.choice(LIGHTWEIGHT_ENDPOINTS)
        self.client.request(
            method=ep["method"],
            url=ep["path"],
            name=f"Ops: {ep['path']}",
            timeout=10.0,
        )
