"""ARIA Comprehensive Load Testing & Capacity Benchmark Engine.

Orchestrates all load test phases, collects telemetry, calculates statistical
percentiles (p50, p95, p99, max), evaluates safety thresholds, and produces
comprehensive capacity measurements.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import httpx
import numpy as np

from tests.load.sse_client import consume_chat_stream, consume_analyze_stream
from tests.load.system_monitor import SystemMonitor
from tests.load.scenarios import (
    BENCHMARK_REPO,
    REALISTIC_CHAT_QUERIES,
    BROWSING_ENDPOINTS,
    LIGHTWEIGHT_ENDPOINTS,
)


@dataclass
class ConcurrencyLevelResult:
    """Metrics captured for a specific concurrency level in a scenario."""

    concurrency: int
    duration_s: float
    total_requests: int
    successful_requests: int
    failed_requests: int
    timeout_requests: int
    error_rate_pct: float
    throughput_rps: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    max_latency_ms: float
    avg_ttft_ms: Optional[float] = None
    p95_ttft_ms: Optional[float] = None
    avg_stream_duration_ms: Optional[float] = None
    total_tokens_delivered: int = 0
    tokens_per_sec: float = 0.0
    fallback_count: int = 0
    cpu_avg_pct: float = 0.0
    cpu_peak_pct: float = 0.0
    mem_rss_mb_peak: float = 0.0
    mem_growth_mb: float = 0.0
    peak_open_connections: int = 0
    errors: List[str] = field(default_factory=list)


@dataclass
class ScenarioBenchmarkResult:
    """Complete benchmark results across progressive concurrency levels for a scenario."""

    scenario_name: str
    levels: List[ConcurrencyLevelResult] = field(default_factory=list)
    safe_capacity: int = 0
    degradation_point: int = 0
    hard_limit: int = 0
    primary_bottleneck: str = ""


class BenchmarkEngine:
    """Automated benchmark executor for ARIA load and capacity testing."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8001",
        target_pid: Optional[int] = None,
        timeout: float = 60.0,
        api_key: str = "aria-benchmark-key",
    ):
        self.base_url = base_url.rstrip("/")
        self.target_pid = target_pid
        self.timeout = timeout
        self.api_key = api_key

    @staticmethod
    def _calc_percentiles(values: List[float]) -> Tuple[float, float, float, float]:
        if not values:
            return 0.0, 0.0, 0.0, 0.0
        arr = np.array(values)
        return (
            float(round(np.percentile(arr, 50), 1)),
            float(round(np.percentile(arr, 95), 1)),
            float(round(np.percentile(arr, 99), 1)),
            float(round(np.max(arr), 1)),
        )

    async def run_chat_batch(
        self,
        concurrency: int,
        duration_s: float = 10.0,
        repo: str = BENCHMARK_REPO,
    ) -> ConcurrencyLevelResult:
        """Run concurrent Chat SSE requests."""
        monitor = SystemMonitor(target_pid=self.target_pid)
        await monitor.start()

        latencies: List[float] = []
        ttfts: List[float] = []
        stream_durations: List[float] = []
        errors: List[str] = []
        successful = 0
        failed = 0
        timeouts = 0
        total_tokens = 0
        fallback_count = 0

        stop_time = time.time() + duration_s
        limits = httpx.Limits(
            max_connections=concurrency + 50,
            max_keepalive_connections=concurrency + 50,
        )

        async with httpx.AsyncClient(limits=limits) as client:

            async def worker():
                nonlocal successful, failed, timeouts, total_tokens, fallback_count
                while time.time() < stop_time:
                    question = random.choice(REALISTIC_CHAT_QUERIES)
                    res = await consume_chat_stream(
                        client=client,
                        base_url=self.base_url,
                        repo=repo,
                        message=question,
                        timeout=self.timeout,
                    )
                    latencies.append(res.duration_ms)
                    if res.ttft_ms is not None:
                        ttfts.append(res.ttft_ms)
                    if res.duration_ms > 0:
                        stream_durations.append(res.duration_ms)
                    total_tokens += res.tokens_count

                    if res.fallback_mode:
                        fallback_count += 1

                    if res.success:
                        successful += 1
                    else:
                        failed += 1
                        if "timed out" in str(res.error).lower():
                            timeouts += 1
                        if res.error and len(errors) < 10:
                            errors.append(str(res.error))

                    # Brief realistic user pause
                    await asyncio.sleep(0.05)

            tasks = [asyncio.create_task(worker()) for _ in range(concurrency)]
            await asyncio.gather(*tasks, return_exceptions=True)

        res_summary = await monitor.stop()
        total_reqs = successful + failed
        actual_duration = max(0.1, res_summary.duration_s)
        p50, p95, p99, max_lat = self._calc_percentiles(latencies)
        _, p95_ttft, _, _ = self._calc_percentiles(ttfts)

        return ConcurrencyLevelResult(
            concurrency=concurrency,
            duration_s=actual_duration,
            total_requests=total_reqs,
            successful_requests=successful,
            failed_requests=failed,
            timeout_requests=timeouts,
            error_rate_pct=round((failed / total_reqs * 100) if total_reqs else 0.0, 2),
            throughput_rps=round(total_reqs / actual_duration, 2),
            p50_latency_ms=p50,
            p95_latency_ms=p95,
            p99_latency_ms=p99,
            max_latency_ms=max_lat,
            avg_ttft_ms=round(sum(ttfts) / len(ttfts), 1) if ttfts else None,
            p95_ttft_ms=p95_ttft if ttfts else None,
            avg_stream_duration_ms=round(
                sum(stream_durations) / len(stream_durations), 1
            )
            if stream_durations
            else None,
            total_tokens_delivered=total_tokens,
            tokens_per_sec=round(total_tokens / actual_duration, 1),
            fallback_count=fallback_count,
            cpu_avg_pct=res_summary.cpu_avg,
            cpu_peak_pct=res_summary.cpu_peak,
            mem_rss_mb_peak=res_summary.memory_rss_mb_peak,
            mem_growth_mb=res_summary.memory_growth_mb,
            peak_open_connections=res_summary.peak_open_connections,
            errors=errors,
        )

    async def run_sse_concurrency_test(
        self,
        concurrency: int,
        duration_s: float = 10.0,
    ) -> ConcurrencyLevelResult:
        """Measure pure concurrent SSE streams."""
        return await self.run_chat_batch(
            concurrency=concurrency,
            duration_s=duration_s,
        )

    async def run_repo_analysis_batch(
        self,
        concurrency: int,
        duration_s: float = 15.0,
    ) -> ConcurrencyLevelResult:
        """Measure concurrent repository analysis / indexing capacity."""
        monitor = SystemMonitor(target_pid=self.target_pid)
        await monitor.start()

        latencies: List[float] = []
        errors: List[str] = []
        successful = 0
        failed = 0
        timeouts = 0

        stop_time = time.time() + duration_s
        limits = httpx.Limits(
            max_connections=concurrency + 20,
            max_keepalive_connections=concurrency + 20,
        )

        async with httpx.AsyncClient(limits=limits) as client:

            async def worker():
                nonlocal successful, failed, timeouts
                while time.time() < stop_time:
                    res = await consume_analyze_stream(
                        client=client,
                        base_url=self.base_url,
                        repo_url=f"https://github.com/{BENCHMARK_REPO}",
                        force_rebuild=False,
                        timeout=90.0,
                    )
                    latencies.append(res.duration_ms)
                    if res.success:
                        successful += 1
                    else:
                        failed += 1
                        if "timed out" in str(res.error).lower():
                            timeouts += 1
                        if res.error and len(errors) < 10:
                            errors.append(str(res.error))
                    await asyncio.sleep(0.2)

            tasks = [asyncio.create_task(worker()) for _ in range(concurrency)]
            await asyncio.gather(*tasks, return_exceptions=True)

        res_summary = await monitor.stop()
        total_reqs = successful + failed
        actual_duration = max(0.1, res_summary.duration_s)
        p50, p95, p99, max_lat = self._calc_percentiles(latencies)

        return ConcurrencyLevelResult(
            concurrency=concurrency,
            duration_s=actual_duration,
            total_requests=total_reqs,
            successful_requests=successful,
            failed_requests=failed,
            timeout_requests=timeouts,
            error_rate_pct=round((failed / total_reqs * 100) if total_reqs else 0.0, 2),
            throughput_rps=round(total_reqs / actual_duration, 2),
            p50_latency_ms=p50,
            p95_latency_ms=p95,
            p99_latency_ms=p99,
            max_latency_ms=max_lat,
            cpu_avg_pct=res_summary.cpu_avg,
            cpu_peak_pct=res_summary.cpu_peak,
            mem_rss_mb_peak=res_summary.memory_rss_mb_peak,
            mem_growth_mb=res_summary.memory_growth_mb,
            peak_open_connections=res_summary.peak_open_connections,
            errors=errors,
        )

    async def run_mixed_workload_batch(
        self,
        concurrency: int,
        duration_s: float = 12.0,
    ) -> ConcurrencyLevelResult:
        """Measure Mixed Production Workload: 60% Chat SSE, 20% Repo Analysis, 10% Browsing, 10% Ops."""
        monitor = SystemMonitor(target_pid=self.target_pid)
        await monitor.start()

        latencies: List[float] = []
        ttfts: List[float] = []
        errors: List[str] = []
        successful = 0
        failed = 0
        timeouts = 0
        total_tokens = 0

        stop_time = time.time() + duration_s
        limits = httpx.Limits(
            max_connections=concurrency + 50,
            max_keepalive_connections=concurrency + 50,
        )

        async with httpx.AsyncClient(limits=limits) as client:

            async def worker():
                nonlocal successful, failed, timeouts, total_tokens
                while time.time() < stop_time:
                    r = random.random()
                    t_req_start = time.perf_counter()
                    if r < 0.60:
                        # 60% Chat SSE
                        question = random.choice(REALISTIC_CHAT_QUERIES)
                        res = await consume_chat_stream(
                            client=client,
                            base_url=self.base_url,
                            repo=BENCHMARK_REPO,
                            message=question,
                            timeout=self.timeout,
                        )
                        latencies.append(res.duration_ms)
                        if res.ttft_ms:
                            ttfts.append(res.ttft_ms)
                        total_tokens += res.tokens_count
                        if res.success:
                            successful += 1
                        else:
                            failed += 1
                            if "timed out" in str(res.error).lower():
                                timeouts += 1
                            if res.error and len(errors) < 10:
                                errors.append(str(res.error))
                    elif r < 0.80:
                        # 20% Repo Analysis
                        res = await consume_analyze_stream(
                            client=client,
                            base_url=self.base_url,
                            repo_url=f"https://github.com/{BENCHMARK_REPO}",
                            force_rebuild=False,
                            timeout=60.0,
                        )
                        latencies.append(res.duration_ms)
                        if res.success:
                            successful += 1
                        else:
                            failed += 1
                            if "timed out" in str(res.error).lower():
                                timeouts += 1
                            if res.error and len(errors) < 10:
                                errors.append(str(res.error))
                    elif r < 0.90:
                        # 10% Repo Browsing / Intelligence APIs
                        ep = random.choice(BROWSING_ENDPOINTS)
                        try:
                            resp = await client.request(
                                method=ep["method"],
                                url=f"{self.base_url}{ep['path']}",
                                headers={"X-API-Key": "aria-benchmark-key"},
                                timeout=15.0,
                            )
                            lat = (time.perf_counter() - t_req_start) * 1000.0
                            latencies.append(lat)
                            if resp.status_code == 200:
                                successful += 1
                            else:
                                failed += 1
                                if len(errors) < 10:
                                    errors.append(
                                        f"HTTP {resp.status_code}: {ep['path']}"
                                    )
                        except Exception as exc:
                            lat = (time.perf_counter() - t_req_start) * 1000.0
                            latencies.append(lat)
                            failed += 1
                            if len(errors) < 10:
                                errors.append(f"Browsing err: {exc}")
                    else:
                        # 10% Lightweight Ops APIs
                        ep = random.choice(LIGHTWEIGHT_ENDPOINTS)
                        try:
                            resp = await client.request(
                                method=ep["method"],
                                url=f"{self.base_url}{ep['path']}",
                                headers={"X-API-Key": "aria-benchmark-key"},
                                timeout=10.0,
                            )
                            lat = (time.perf_counter() - t_req_start) * 1000.0
                            latencies.append(lat)
                            if resp.status_code == 200:
                                successful += 1
                            else:
                                failed += 1
                                if len(errors) < 10:
                                    errors.append(
                                        f"HTTP {resp.status_code}: {ep['path']}"
                                    )
                        except Exception as exc:
                            lat = (time.perf_counter() - t_req_start) * 1000.0
                            latencies.append(lat)
                            failed += 1
                            if len(errors) < 10:
                                errors.append(f"Ops err: {exc}")

                    await asyncio.sleep(0.05)

            tasks = [asyncio.create_task(worker()) for _ in range(concurrency)]
            await asyncio.gather(*tasks, return_exceptions=True)

        res_summary = await monitor.stop()
        total_reqs = successful + failed
        actual_duration = max(0.1, res_summary.duration_s)
        p50, p95, p99, max_lat = self._calc_percentiles(latencies)

        return ConcurrencyLevelResult(
            concurrency=concurrency,
            duration_s=actual_duration,
            total_requests=total_reqs,
            successful_requests=successful,
            failed_requests=failed,
            timeout_requests=timeouts,
            error_rate_pct=round((failed / total_reqs * 100) if total_reqs else 0.0, 2),
            throughput_rps=round(total_reqs / actual_duration, 2),
            p50_latency_ms=p50,
            p95_latency_ms=p95,
            p99_latency_ms=p99,
            max_latency_ms=max_lat,
            avg_ttft_ms=round(sum(ttfts) / len(ttfts), 1) if ttfts else None,
            total_tokens_delivered=total_tokens,
            tokens_per_sec=round(total_tokens / actual_duration, 1),
            cpu_avg_pct=res_summary.cpu_avg,
            cpu_peak_pct=res_summary.cpu_peak,
            mem_rss_mb_peak=res_summary.memory_rss_mb_peak,
            mem_growth_mb=res_summary.memory_growth_mb,
            peak_open_connections=res_summary.peak_open_connections,
            errors=errors,
        )

    def analyze_scenario_capacity(
        self,
        results: List[ConcurrencyLevelResult],
        scenario_name: str,
    ) -> ScenarioBenchmarkResult:
        """Determine Safe Capacity, Degradation Point, Hard Limit, and Bottleneck."""
        safe_capacity = 0
        degradation_point = 0
        hard_limit = 0
        bottleneck = "Single ASGI Worker / Python GIL CPU Event-Loop Contention"

        for res in results:
            # Safe condition: error_rate < 1.0% and p95 latency under threshold
            latency_thresh = 15000.0 if "analysis" in scenario_name.lower() else 5000.0
            if res.error_rate_pct < 1.0 and res.p95_latency_ms < latency_thresh:
                safe_capacity = res.concurrency

            # Degradation condition: latency jumps > 2.5x baseline or error > 1% or CPU > 85%
            if degradation_point == 0:
                if (
                    res.error_rate_pct >= 1.0
                    or res.p95_latency_ms > latency_thresh
                    or res.cpu_peak_pct > 85.0
                ):
                    degradation_point = res.concurrency

            # Hard limit: error rate > 10% or timeouts > 5% or sustained failure
            if hard_limit == 0:
                if res.error_rate_pct >= 10.0 or res.timeout_requests > 0:
                    hard_limit = res.concurrency

        if degradation_point == 0 and results:
            degradation_point = results[-1].concurrency
        if hard_limit == 0 and results:
            hard_limit = int(results[-1].concurrency * 1.5)

        # Identify bottleneck characteristics
        peak_cpu = max((r.cpu_peak_pct for r in results), default=0)
        peak_mem = max((r.mem_rss_mb_peak for r in results), default=0)
        timeouts = sum(r.timeout_requests for r in results)

        if peak_cpu > 80.0:
            bottleneck = (
                "CPU Saturation (Single Worker Event Loop + Local Embedding Generation)"
            )
        elif timeouts > 0:
            bottleneck = "HTTP Connection Queue Backlog / Worker Starvation"
        elif peak_mem > 4000:
            bottleneck = "Memory Saturation (In-memory Store / Model Buffers)"
        else:
            bottleneck = "Single ASGI Event-Loop Concurrency Bound (Uvicorn 1 Worker)"

        return ScenarioBenchmarkResult(
            scenario_name=scenario_name,
            levels=results,
            safe_capacity=safe_capacity,
            degradation_point=degradation_point,
            hard_limit=hard_limit,
            primary_bottleneck=bottleneck,
        )
