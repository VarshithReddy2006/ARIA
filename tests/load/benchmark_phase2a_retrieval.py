"""ARIA Phase 2A: Low-Risk ChromaDB Retrieval Optimization Benchmark Suite.

Executes:
  1. Isolated Retrieval Microbenchmarks:
     - Cold vs Warm Latency (p50, p95, p99, avg)
     - Cache Hit vs Miss timings
     - Repeated-Query Workload across 1, 5, 10, 25, 50, 75 concurrent requests
     - Diverse-Query Workload across 1, 5, 10, 25, 50, 75 concurrent requests
     - Memory and Cache metrics
  2. Full Chat End-to-End Workload (4 Workers):
     - 25, 50, 75, 100 users with realistic mixed query distribution
     - Measures: Success rate, Throughput, p50/p95/p99 latency, TTFT, Chroma retrieval time, Cache hit rate
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from typing import Any, Dict
import httpx
import numpy as np

# Ensure root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from core.config import settings
from memory.chroma_store import ChromaStore
from services.chat.retrieval import intelligent_retrieve
from services.chat.retrieval_cache import retrieval_cache
from services.embedding_service import EmbeddingService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("benchmark_phase2a")

REPO_NAME = "VarshithReddy2006/Repo-Intelligence-Agent"
DEFAULT_BENCHMARK_KEY = "aria-perf-eval-key-2026-secure"

REPEATED_QUERIES = [
    "Explain backend/api.py routing",
    "How does the provider circuit breaker work?",
    "Where is the vector database ChromaStore defined?",
    "Explain retrieval pipeline token budgeting",
    "How does the embedding service cache work?",
]

DIVERSE_QUERIES = [
    f"Explain component architecture and dependency graph query {i} for module {i * 7}"
    for i in range(100)
]


def run_isolated_microbenchmarks(
    chroma_store: ChromaStore, embedding_service: EmbeddingService
) -> Dict[str, Any]:
    logger.info(
        "======================================================================"
    )
    logger.info("PHASE 1: ISOLATED RETRIEVAL MICROBENCHMARKS")
    logger.info(
        "======================================================================"
    )

    # 1. Cold vs Warm Latency (Single Query)
    retrieval_cache.invalidate_all()
    retrieval_cache.reset_metrics()

    test_query = "How does the provider circuit breaker work?"

    # Cold Miss
    t0 = time.perf_counter()
    chunks_cold, metrics_cold = intelligent_retrieve(
        question=test_query,
        repo_name=REPO_NAME,
        embedding_service=embedding_service,
        chroma_store=chroma_store,
        use_cache=True,
    )
    cold_total_ms = (time.perf_counter() - t0) * 1000.0

    # Warm Hit
    t0 = time.perf_counter()
    chunks_warm, metrics_warm = intelligent_retrieve(
        question=test_query,
        repo_name=REPO_NAME,
        embedding_service=embedding_service,
        chroma_store=chroma_store,
        use_cache=True,
    )
    warm_total_ms = (time.perf_counter() - t0) * 1000.0

    logger.info(
        "  Cold Miss Retrieval: %6.2f ms (Search: %.2f ms, Embed: %.2f ms)",
        cold_total_ms,
        metrics_cold.get("search_ms", 0),
        metrics_cold.get("embed_ms", 0),
    )
    logger.info(
        "  Warm Hit Retrieval:  %6.2f ms (Cache Hit: %s)",
        warm_total_ms,
        metrics_warm.get("cache_hit"),
    )

    # Warm Latency Distribution (100 repetitions of cached retrieval)
    warm_timings = []
    for _ in range(100):
        t0 = time.perf_counter()
        intelligent_retrieve(
            question=test_query,
            repo_name=REPO_NAME,
            embedding_service=embedding_service,
            chroma_store=chroma_store,
            use_cache=True,
        )
        warm_timings.append((time.perf_counter() - t0) * 1000.0)

    warm_p50 = float(np.percentile(warm_timings, 50))
    warm_p95 = float(np.percentile(warm_timings, 95))
    warm_p99 = float(np.percentile(warm_timings, 99))
    warm_avg = float(np.mean(warm_timings))

    logger.info(
        "  Warm Cached Stats:   avg=%.3f ms | p50=%.3f ms | p95=%.3f ms | p99=%.3f ms",
        warm_avg,
        warm_p50,
        warm_p95,
        warm_p99,
    )

    # 2. Concurrency Scaling Matrix: Repeated vs Diverse Workloads
    concurrency_levels = [1, 5, 10, 25, 50, 75]
    repeated_scaling = {}
    diverse_scaling = {}

    logger.info(
        "----------------------------------------------------------------------"
    )
    logger.info("REPEATED-QUERY WORKLOAD CONCURRENCY SCALING")
    logger.info(
        "----------------------------------------------------------------------"
    )

    # Pre-warm cache for the repeated pool
    for q in REPEATED_QUERIES:
        intelligent_retrieve(
            q, REPO_NAME, embedding_service, chroma_store, use_cache=True
        )

    for c in concurrency_levels:
        retrieval_cache.reset_metrics()

        async def run_repeated_batch(num_concurrency: int):
            loop = asyncio.get_running_loop()
            queries = [
                REPEATED_QUERIES[i % len(REPEATED_QUERIES)]
                for i in range(num_concurrency)
            ]

            async def single_worker(q_str: str):
                t_start = time.perf_counter()
                res = await loop.run_in_executor(
                    None,
                    lambda: intelligent_retrieve(
                        question=q_str,
                        repo_name=REPO_NAME,
                        embedding_service=embedding_service,
                        chroma_store=chroma_store,
                        use_cache=True,
                    ),
                )
                dur = (time.perf_counter() - t_start) * 1000.0
                return dur, res[1].get("cache_hit", False)

            t_total_start = time.perf_counter()
            results = await asyncio.gather(*(single_worker(q) for q in queries))
            total_wall_s = time.perf_counter() - t_total_start
            return results, total_wall_s

        repeated_results, rep_wall_s = asyncio.run(run_repeated_batch(c))
        rep_durs = [r[0] for r in repeated_results]
        rep_hits = sum(1 for r in repeated_results if r[1])
        repeated_scaling[str(c)] = {
            "concurrency": c,
            "throughput_rps": round(c / rep_wall_s, 2) if rep_wall_s > 0 else 0,
            "avg_latency_ms": round(float(np.mean(rep_durs)), 2),
            "p50_latency_ms": round(float(np.percentile(rep_durs, 50)), 2),
            "p95_latency_ms": round(float(np.percentile(rep_durs, 95)), 2),
            "hit_rate_pct": round((rep_hits / c) * 100.0, 1),
        }
        logger.info(
            "  Repeated Concurrency %2d: Throughput=%8.1f rps | p50=%5.2f ms | p95=%5.2f ms | Hit Rate=%.1f%%",
            c,
            repeated_scaling[str(c)]["throughput_rps"],
            repeated_scaling[str(c)]["p50_latency_ms"],
            repeated_scaling[str(c)]["p95_latency_ms"],
            repeated_scaling[str(c)]["hit_rate_pct"],
        )

    logger.info(
        "----------------------------------------------------------------------"
    )
    logger.info("DIVERSE-QUERY WORKLOAD CONCURRENCY SCALING (100% UNIQUE QUERIES)")
    logger.info(
        "----------------------------------------------------------------------"
    )

    for c in concurrency_levels:
        retrieval_cache.invalidate_all()
        retrieval_cache.reset_metrics()

        async def run_diverse_batch(num_concurrency: int):
            loop = asyncio.get_running_loop()
            queries = [
                DIVERSE_QUERIES[i % len(DIVERSE_QUERIES)]
                for i in range(num_concurrency)
            ]

            async def single_worker(q_str: str):
                t_start = time.perf_counter()
                res = await loop.run_in_executor(
                    None,
                    lambda: intelligent_retrieve(
                        question=q_str,
                        repo_name=REPO_NAME,
                        embedding_service=embedding_service,
                        chroma_store=chroma_store,
                        use_cache=True,
                    ),
                )
                dur = (time.perf_counter() - t_start) * 1000.0
                return dur, res[1].get("cache_hit", False)

            t_total_start = time.perf_counter()
            results = await asyncio.gather(*(single_worker(q) for q in queries))
            total_wall_s = time.perf_counter() - t_total_start
            return results, total_wall_s

        diverse_results, div_wall_s = asyncio.run(run_diverse_batch(c))
        div_durs = [r[0] for r in diverse_results]
        div_hits = sum(1 for r in diverse_results if r[1])
        diverse_scaling[str(c)] = {
            "concurrency": c,
            "throughput_rps": round(c / div_wall_s, 2) if div_wall_s > 0 else 0,
            "avg_latency_ms": round(float(np.mean(div_durs)), 2),
            "p50_latency_ms": round(float(np.percentile(div_durs, 50)), 2),
            "p95_latency_ms": round(float(np.percentile(div_durs, 95)), 2),
            "hit_rate_pct": round((div_hits / c) * 100.0, 1),
        }
        logger.info(
            "  Diverse  Concurrency %2d: Throughput=%8.1f rps | p50=%5.2f ms | p95=%5.2f ms | Hit Rate=%.1f%%",
            c,
            diverse_scaling[str(c)]["throughput_rps"],
            diverse_scaling[str(c)]["p50_latency_ms"],
            diverse_scaling[str(c)]["p95_latency_ms"],
            diverse_scaling[str(c)]["hit_rate_pct"],
        )

    return {
        "cold_miss_ms": round(cold_total_ms, 2),
        "warm_hit_ms": round(warm_total_ms, 2),
        "speedup_ratio": round(cold_total_ms / max(0.01, warm_total_ms), 2),
        "warm_distribution": {
            "avg_ms": round(warm_avg, 3),
            "p50_ms": round(warm_p50, 3),
            "p95_ms": round(warm_p95, 3),
            "p99_ms": round(warm_p99, 3),
        },
        "repeated_workload_scaling": repeated_scaling,
        "diverse_workload_scaling": diverse_scaling,
        "cache_metrics": retrieval_cache.get_metrics(),
    }


async def wait_for_server(url: str, timeout: float = 45.0) -> bool:
    deadline = time.time() + timeout
    async with httpx.AsyncClient() as client:
        while time.time() < deadline:
            try:
                r = await client.get(url, timeout=1.5)
                if r.status_code == 200:
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.5)
    return False


DEFAULT_BENCHMARK_KEY = "aria-benchmark-key"


def start_multi_worker_server(
    port: int = 8000, workers: int = 4, mock_port: int = 8999
) -> subprocess.Popen:
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    env = os.environ.copy()
    env["APP_ENV"] = "production"
    env["API_KEY"] = DEFAULT_BENCHMARK_KEY
    env["ALLOWED_HOSTS"] = json.dumps(["127.0.0.1", "localhost", "testserver"])
    env["API_SERVER_PORT"] = str(port)
    env["RATE_LIMIT_PER_MINUTE"] = "100000"
    env["LLM_PROVIDER"] = "deepseek"
    env["DEEPSEEK_BASE_URL"] = f"http://127.0.0.1:{mock_port}/v1"
    env["DEEPSEEK_API_KEY"] = "mock-key-phase2a"
    env["WORKER_COUNT"] = str(workers)
    env["WEB_CONCURRENCY"] = str(workers)
    env["ARIA_WORKERS"] = str(workers)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = root_dir

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
        cwd=root_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc


async def run_full_chat_validation_suite() -> Dict[str, Any]:
    logger.info(
        "======================================================================"
    )
    logger.info("PHASE 2: FULL CHAT END-TO-END VALIDATION (4 UVICORN WORKERS)")
    logger.info(
        "======================================================================"
    )

    from tests.load.benchmark_engine import BenchmarkEngine
    from tests.load.mock_provider_server import MockProviderServer

    port = 8000
    mock_port = 8999
    host = f"http://127.0.0.1:{port}"
    api_key = DEFAULT_BENCHMARK_KEY

    # 1. Start Mock Provider and Multi-worker server
    mock_server = MockProviderServer(port=mock_port)
    await mock_server.start()

    aria_proc = start_multi_worker_server(port=port, workers=4, mock_port=mock_port)
    is_ready = await wait_for_server(f"{host}/api/v1/health", timeout=45.0)
    if not is_ready:
        logger.error("ARIA server failed to become ready.")
        aria_proc.kill()
        await mock_server.stop()
        return {}

    concurrency_targets = [25, 50, 75, 100]
    chat_results = {}

    try:
        engine = BenchmarkEngine(
            base_url=host,
            api_key=api_key,
            timeout=65.0,
        )

        for c in concurrency_targets:
            logger.info("  --> Benchmarking %3d Concurrent Users under 4 Workers...", c)
            duration = 20.0 if c <= 50 else 25.0
            res = await engine.run_chat_batch(
                concurrency=c,
                duration_s=duration,
                repo=REPO_NAME,
            )

            chat_results[str(c)] = {
                "concurrency": c,
                "total_requests": res.total_requests,
                "successful_requests": res.successful_requests,
                "failed_requests": res.failed_requests,
                "error_rate_pct": round(res.error_rate_pct, 1),
                "throughput_rps": round(res.throughput_rps, 2),
                "p50_latency_ms": round(res.p50_latency_ms, 2),
                "p95_latency_ms": round(res.p95_latency_ms, 2),
                "p99_latency_ms": round(res.p99_latency_ms, 2),
                "avg_ttft_ms": round(
                    res.avg_ttft_ms if res.avg_ttft_ms is not None else 0.0, 2
                ),
                "p95_ttft_ms": round(
                    res.p95_ttft_ms if res.p95_ttft_ms is not None else 0.0, 2
                ),
            }
            logger.info(
                "      Result: Req=%3d (Succ=%3d, Fail=%2d) | Throughput=%.2f rps | p50=%7.1fms | p95=%7.1fms | Error Rate=%.1f%%",
                res.total_requests,
                res.successful_requests,
                res.failed_requests,
                res.throughput_rps,
                res.p50_latency_ms,
                res.p95_latency_ms,
                res.error_rate_pct,
            )

    finally:
        try:
            aria_proc.kill()
        except Exception:
            pass
        try:
            await mock_server.stop()
        except Exception:
            pass

    return chat_results


def main():
    chroma_store = ChromaStore(persist_directory=settings.chroma_db_path)
    embedding_service = EmbeddingService()

    micro_results = run_isolated_microbenchmarks(chroma_store, embedding_service)

    chat_results = asyncio.run(run_full_chat_validation_suite())

    final_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "microbenchmarks": micro_results,
        "chat_validation": chat_results,
    }

    output_path = "docs/performance/retrieval_cache_evaluation_results.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_data, f, indent=2)

    logger.info(
        "======================================================================"
    )
    logger.info("BENCHMARK RUN COMPLETE - RESULTS SAVED TO %s", output_path)
    logger.info(
        "======================================================================"
    )


if __name__ == "__main__":
    main()
