"""Multi-Worker Scalability Benchmark Runner for ARIA.

Evaluates ARIA under multi-worker process deployment (e.g., 4 Uvicorn workers)
and compares directly against the single-worker baseline documented in:
  docs/performance/ARIA_CAPACITY_REPORT.md

Tests progressive chat concurrency levels:
  1, 5, 10, 25, 50, 75, 100 users.

Measures:
  - Total requests, successes, failures, error rate
  - Throughput (req/sec)
  - Time to First Token (TTFT)
  - Latency percentiles (p50, p95, p99)
  - CPU peak utilization and Memory RSS impact
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import subprocess
import sys
import time
from typing import Any, Dict, List
import httpx
import psutil

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from tests.load.mock_provider_server import MockProviderServer
from tests.load.benchmark_engine import BenchmarkEngine, ConcurrencyLevelResult

DEFAULT_BENCHMARK_KEY = "aria-benchmark-key"

# Authoritative baseline from docs/performance/ARIA_CAPACITY_REPORT.md (Single Worker)
BASELINE_SINGLE_WORKER: Dict[int, Dict[str, Any]] = {
    1: {
        "concurrency": 1,
        "successes": 7,
        "failures": 0,
        "error_rate_pct": 0.0,
        "throughput_rps": 0.8,
        "ttft_ms": 1162.2,
        "p50_ms": 803.1,
        "p95_ms": 2578.0,
        "status": "Safe Capacity",
    },
    5: {
        "concurrency": 5,
        "successes": 14,
        "failures": 0,
        "error_rate_pct": 0.0,
        "throughput_rps": 1.4,
        "ttft_ms": 3266.8,
        "p50_ms": 3388.8,
        "p95_ms": 4164.1,
        "status": "Safe Capacity",
    },
    10: {
        "concurrency": 10,
        "successes": 20,
        "failures": 0,
        "error_rate_pct": 0.0,
        "throughput_rps": 1.4,
        "ttft_ms": 6842.1,
        "p50_ms": 6881.2,
        "p95_ms": 6909.6,
        "status": "Safe Capacity",
    },
    25: {
        "concurrency": 25,
        "successes": 25,
        "failures": 0,
        "error_rate_pct": 0.0,
        "throughput_rps": 1.6,
        "ttft_ms": 14789.5,
        "p50_ms": 14362.7,
        "p95_ms": 15923.7,
        "status": "Upper Safe Limit",
    },
    50: {
        "concurrency": 50,
        "successes": 50,
        "failures": 0,
        "error_rate_pct": 0.0,
        "throughput_rps": 1.6,
        "ttft_ms": 24472.6,
        "p50_ms": 24837.3,
        "p95_ms": 31390.1,
        "status": "Degradation Point",
    },
    75: {
        "concurrency": 75,
        "successes": 75,
        "failures": 0,
        "error_rate_pct": 0.0,
        "throughput_rps": 1.2,
        "ttft_ms": 43219.9,
        "p50_ms": 43908.8,
        "p95_ms": 60094.5,
        "status": "High Latency Queue",
    },
    100: {
        "concurrency": 100,
        "successes": 74,
        "failures": 26,
        "error_rate_pct": 26.0,
        "throughput_rps": 1.7,
        "ttft_ms": 43758.1,
        "p50_ms": 48155.5,
        "p95_ms": 60047.6,
        "status": "Hard Limit (26% Drops)",
    },
}


async def wait_for_server(health_url: str, timeout: float = 60.0) -> bool:
    """Poll health endpoint until 200 OK."""
    stop = time.time() + timeout
    async with httpx.AsyncClient(timeout=2.0) as client:
        while time.time() < stop:
            try:
                resp = await client.get(
                    health_url, headers={"X-API-Key": DEFAULT_BENCHMARK_KEY}
                )
                if resp.status_code == 200:
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.3)
    return False


async def start_multi_worker_backend(
    port: int,
    workers: int = 4,
    mock_port: int = 8999,
) -> subprocess.Popen:
    """Launch ARIA with configurable worker count."""
    env = os.environ.copy()
    env["APP_ENV"] = "production"
    env["API_KEY"] = DEFAULT_BENCHMARK_KEY
    env["ALLOWED_HOSTS"] = json.dumps(["127.0.0.1", "localhost", "testserver"])
    env["API_SERVER_PORT"] = str(port)
    env["RATE_LIMIT_PER_MINUTE"] = "100000"
    env["LLM_PROVIDER"] = "deepseek"
    env["DEEPSEEK_BASE_URL"] = f"http://127.0.0.1:{mock_port}/v1"
    env["DEEPSEEK_API_KEY"] = "mock-key-capacity-eval"
    env["WORKER_COUNT"] = str(workers)
    env["WEB_CONCURRENCY"] = str(workers)
    env["ARIA_WORKERS"] = str(workers)
    env["PYTHONUNBUFFERED"] = "1"

    venv_py = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../.venv/Scripts/python.exe")
    )
    py_exec = venv_py if os.path.exists(venv_py) else sys.executable

    cmd = [
        py_exec,
        "-m",
        "uvicorn",
        "backend.api:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--workers",
        str(workers),
        "--log-level",
        "warning",
    ]

    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    healthy = await wait_for_server(
        f"http://127.0.0.1:{port}/api/v1/health", timeout=60.0
    )
    if not healthy:
        try:
            proc.kill()
        except Exception:
            pass
        raise RuntimeError(
            f"Multi-worker server on port {port} ({workers} workers) failed health check."
        )

    return proc


def get_all_child_pids(parent_pid: int) -> List[int]:
    """Retrieve all worker process PIDs spawned by the master Uvicorn process."""
    pids = [parent_pid]
    try:
        parent = psutil.Process(parent_pid)
        for child in parent.children(recursive=True):
            pids.append(child.pid)
    except Exception:
        pass
    return pids


async def run_multi_worker_benchmark(
    worker_count: int = 4,
    app_port: int = 8001,
    mock_port: int = 8999,
) -> Dict[str, Any]:
    """Run full load tests on multi-worker ARIA deployment and produce comparison report."""
    print("=" * 70, flush=True)
    print(
        f"ARIA MULTI-WORKER SCALABILITY BENCHMARK ({worker_count} WORKERS)", flush=True
    )
    print("=" * 70, flush=True)
    print(f"Host OS: {platform.platform()}", flush=True)
    print(
        f"Host CPU Physical / Logical: {psutil.cpu_count(logical=False)} / {psutil.cpu_count(logical=True)}",
        flush=True,
    )
    print(
        f"Host RAM: {round(psutil.virtual_memory().total / (1024**3), 2)} GB",
        flush=True,
    )
    print(f"Worker Processes: {worker_count}", flush=True)
    print("=" * 70, flush=True)

    # 1. Start Mock Provider
    mock_server = MockProviderServer(port=mock_port)
    await mock_server.start()
    print(
        f"[Mock Server] Streaming mock provider active on port {mock_port}", flush=True
    )

    # 2. Start Multi-Worker Backend
    print(
        f"[Backend] Starting ARIA with {worker_count} Uvicorn worker processes on port {app_port}...",
        flush=True,
    )
    server_proc = await start_multi_worker_backend(
        port=app_port, workers=worker_count, mock_port=mock_port
    )
    worker_pids = get_all_child_pids(server_proc.pid)
    print(
        f"[Backend] Multi-worker ARIA online (Master PID: {server_proc.pid}, Worker PIDs: {worker_pids})",
        flush=True,
    )

    engine = BenchmarkEngine(
        base_url=f"http://127.0.0.1:{app_port}",
        api_key=DEFAULT_BENCHMARK_KEY,
        target_pid=server_proc.pid,
    )

    # 3. Progressive Chat Concurrency Ramp: 1, 5, 10, 25, 50, 75, 100
    chat_levels = [1, 5, 10, 25, 50, 75, 100]
    results: List[ConcurrencyLevelResult] = []

    print("\n" + "=" * 70, flush=True)
    print(f"PROGRESSIVE CHAT BENCHMARK ({worker_count} WORKERS)", flush=True)
    print("=" * 70, flush=True)

    for c in chat_levels:
        print(f"--> Testing Concurrency Level {c:3d} active users...", flush=True)
        res = await engine.run_chat_batch(concurrency=c, duration_s=8.0)
        results.append(res)
        print(
            f"    -> Concurrency {c:3d}: Req={res.total_requests:3d} (Succ={res.successful_requests:3d}, Fail={res.failed_requests:2d}) | "
            f"Throughput={res.throughput_rps:5.1f} rps | p50={res.p50_latency_ms:6.1f}ms | p95={res.p95_latency_ms:6.1f}ms | "
            f"TTFT avg={res.avg_ttft_ms}ms | CPU Peak={res.cpu_peak_pct:4.1f}% | RAM Peak={res.mem_rss_mb_peak:.1f}MB",
            flush=True,
        )
        await asyncio.sleep(0.5)

    # 4. Stop Backend and Mock Server
    try:
        server_proc.kill()
    except Exception:
        pass
    await mock_server.stop()

    # 5. Build Comprehensive Comparison Dataset
    comparison_data = []
    for res in results:
        c = res.concurrency
        base = BASELINE_SINGLE_WORKER.get(c, {})

        # Compute speedups and improvements
        base_p95 = base.get("p95_ms", 0.0)
        curr_p95 = res.p95_latency_ms
        p95_improvement_pct = (
            round((base_p95 - curr_p95) / base_p95 * 100, 1) if base_p95 > 0 else 0.0
        )

        base_tput = base.get("throughput_rps", 0.0)
        curr_tput = res.throughput_rps
        tput_gain_x = round(curr_tput / base_tput, 2) if base_tput > 0 else 1.0

        row = {
            "concurrency": c,
            "single_worker": {
                "successes": base.get("successes", 0),
                "failures": base.get("failures", 0),
                "error_rate_pct": base.get("error_rate_pct", 0.0),
                "throughput_rps": base.get("throughput_rps", 0.0),
                "ttft_ms": base.get("ttft_ms", 0.0),
                "p50_ms": base.get("p50_ms", 0.0),
                "p95_ms": base.get("p95_ms", 0.0),
            },
            "multi_worker": {
                "workers": worker_count,
                "total_requests": res.total_requests,
                "successes": res.successful_requests,
                "failures": res.failed_requests,
                "error_rate_pct": res.error_rate_pct,
                "throughput_rps": res.throughput_rps,
                "ttft_ms": res.avg_ttft_ms,
                "p50_ms": res.p50_latency_ms,
                "p95_ms": res.p95_latency_ms,
                "p99_ms": res.p99_latency_ms,
                "cpu_peak_pct": res.cpu_peak_pct,
                "mem_rss_mb_peak": res.mem_rss_mb_peak,
            },
            "delta": {
                "throughput_gain_x": tput_gain_x,
                "p95_latency_improvement_pct": p95_improvement_pct,
                "error_reduction_pct": round(
                    base.get("error_rate_pct", 0.0) - res.error_rate_pct, 1
                ),
            },
        }
        comparison_data.append(row)

    # 6. Analyze Capacity Thresholds
    scenario_res = engine.analyze_scenario_capacity(
        results, f"Multi-Worker Chat ({worker_count} Workers)"
    )
    peak_throughput = max((r.throughput_rps for r in results), default=0.0)

    output = {
        "worker_count": worker_count,
        "hardware": {
            "os": platform.platform(),
            "cpu_physical": psutil.cpu_count(logical=False),
            "cpu_logical": psutil.cpu_count(logical=True),
            "total_ram_gb": round(psutil.virtual_memory().total / (1024**3), 2),
        },
        "capacity_thresholds": {
            "safe_capacity_users": scenario_res.safe_capacity,
            "degradation_point_users": scenario_res.degradation_point,
            "hard_limit_users": scenario_res.hard_limit,
            "peak_throughput_rps": peak_throughput,
            "primary_bottleneck": scenario_res.primary_bottleneck,
        },
        "comparison_table": comparison_data,
    }

    # Save to JSON
    out_json_path = os.path.join(
        "docs", "performance", "multi_worker_benchmark_results.json"
    )
    os.makedirs(os.path.dirname(out_json_path), exist_ok=True)
    with open(out_json_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2)

    print("\n" + "=" * 70, flush=True)
    print("MULTI-WORKER CAPACITY BENCHMARK COMPLETE", flush=True)
    print(
        f"New Safe Capacity: {scenario_res.safe_capacity} Concurrent Users",
        flush=True,
    )
    print(
        f"New Degradation Point: {scenario_res.degradation_point} Concurrent Users",
        flush=True,
    )
    print(f"New Hard Limit: {scenario_res.hard_limit} Concurrent Users", flush=True)
    print(f"Peak Throughput: {peak_throughput} req/sec", flush=True)
    print(f"Results saved to: {out_json_path}", flush=True)
    print("=" * 70, flush=True)

    return output


if __name__ == "__main__":
    workers = int(os.getenv("WORKER_COUNT") or os.getenv("ARIA_WORKERS") or 4)
    asyncio.run(run_multi_worker_benchmark(worker_count=workers))
