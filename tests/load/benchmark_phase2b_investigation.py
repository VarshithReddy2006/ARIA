"""ARIA Phase 2B: Vector Retrieval Architecture Investigation Suite.

Investigates:
  1. Fine-Grained Retrieval Path Instrumentation (wall vs CPU time, embedding, ChromaDB search, BM25, enrichment).
  2. Concurrency Contention on Unique Queries (1, 5, 10, 25, 50, 75, 100 concurrency).
  3. Worker Isolation Matrix (1, 2, 4, 6, 8 workers across 25, 50, 75, 100 concurrency).
  4. Read/Write Storage Contention (Read-Only, Write-Only, 80/20 Mixed).
  5. Cache Attribution 4-Quadrant Matrix (LRU on/off x Repeated/Unique).
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from typing import Any, Dict, List
import httpx
import numpy as np
import psutil

# Ensure root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from core.config import settings
from memory.chroma_store import ChromaStore
from services.chat.retrieval import intelligent_retrieve
from services.chat.retrieval_cache import retrieval_cache
from services.embedding_service import EmbeddingService
from tests.load.mock_provider_server import MockProviderServer
from tests.load.benchmark_engine import BenchmarkEngine

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("investigation_phase2b")

REPO_NAME = "VarshithReddy2006/Repo-Intelligence-Agent"
DEFAULT_BENCHMARK_KEY = "aria-benchmark-key"

REPEATED_QUERIES = [
    "Explain backend/api.py routing",
    "How does the provider circuit breaker work?",
    "Where is the vector database ChromaStore defined?",
    "Explain retrieval pipeline token budgeting",
    "How does the embedding service cache work?",
]

# 200 Unique Queries to prevent cache hits during unique benchmarks
UNIQUE_QUERIES = [
    f"Analyze dependency coupling and interface contract for subsystem module_{idx}_{hash(str(idx)) % 10000}"
    for idx in range(250)
]


# ==============================================================================
# PHASE 1: FINE-GRAINED RETRIEVAL PATH INSTRUMENTATION
# ==============================================================================
def run_phase1_retrieval_path_trace(
    chroma_store: ChromaStore, embedding_service: EmbeddingService
) -> Dict[str, Any]:
    logger.info(
        "======================================================================"
    )
    logger.info("PHASE 1: FINE-GRAINED RETRIEVAL PATH INSTRUMENTATION")
    logger.info(
        "======================================================================"
    )

    # Pre-warm embedding model
    embedding_service.generate_embedding("warmup")

    test_query = (
        "What is the architectural role of tree-sitter AST parser in symbol extraction?"
    )

    # Ensure cold cache miss
    retrieval_cache.invalidate_all()

    # Stage 1: Embedding
    t0_embed = time.perf_counter()
    query_vector = embedding_service.generate_embedding(test_query)
    embed_ms = (time.perf_counter() - t0_embed) * 1000.0

    # Stage 2: ChromaDB Query
    t0_chroma = time.perf_counter()
    _ = chroma_store.search_repository(REPO_NAME, query_vector, limit=15)
    chroma_search_ms = (time.perf_counter() - t0_chroma) * 1000.0

    # Stage 3: Full intelligent_retrieve call
    t_start_wall = time.perf_counter()
    t_start_cpu = time.process_time()
    chunks, metrics = intelligent_retrieve(
        question=test_query,
        repo_name=REPO_NAME,
        embedding_service=embedding_service,
        chroma_store=chroma_store,
        use_cache=False,
    )
    total_cpu_ms = (time.process_time() - t_start_cpu) * 1000.0
    total_wall_ms = (time.perf_counter() - t_start_wall) * 1000.0
    full_retrieval_ms = total_wall_ms

    bm25_rerank_ms = metrics.get("rerank_ms", 0.0)
    docs_returned = len(chunks)

    trace_results = {
        "query": test_query,
        "docs_returned": docs_returned,
        "wall_clock_total_ms": round(total_wall_ms, 2),
        "cpu_time_total_ms": round(total_cpu_ms, 2),
        "stages": {
            "query_embedding_ms": round(embed_ms, 2),
            "chromadb_vector_search_ms": round(chroma_search_ms, 2),
            "bm25_scoring_and_rerank_ms": round(bm25_rerank_ms, 2),
            "context_assembly_and_overhead_ms": round(
                max(
                    0.0,
                    full_retrieval_ms - (embed_ms + chroma_search_ms + bm25_rerank_ms),
                ),
                2,
            ),
        },
        "retrieval_metrics": metrics,
    }

    logger.info(
        "  Total Retrieval Wall Time: %7.2f ms | CPU Time: %6.2f ms",
        total_wall_ms,
        total_cpu_ms,
    )
    logger.info("    -> Embedding Generation:   %7.2f ms", embed_ms)
    logger.info("    -> ChromaDB Vector Query:  %7.2f ms", chroma_search_ms)
    logger.info("    -> BM25 Scoring & Rerank:  %7.2f ms", bm25_rerank_ms)
    logger.info(
        "    -> Context Assembly:       %7.2f ms",
        trace_results["stages"]["context_assembly_and_overhead_ms"],
    )

    return trace_results


# ==============================================================================
# PHASE 2: UNIQUE QUERY CONTENTION BENCHMARK
# ==============================================================================
def run_phase2_unique_query_contention(
    chroma_store: ChromaStore, embedding_service: EmbeddingService
) -> Dict[str, Any]:
    logger.info(
        "======================================================================"
    )
    logger.info("PHASE 2: UNIQUE QUERY CONCURRENCY CONTENTION (100% UNIQUE QUERIES)")
    logger.info(
        "======================================================================"
    )

    concurrency_levels = [1, 5, 10, 25, 50, 75, 100]
    results = {}

    for c in concurrency_levels:
        retrieval_cache.invalidate_all()
        retrieval_cache.reset_metrics()

        process = psutil.Process()
        process.cpu_percent(interval=None)
        mem_start_mb = process.memory_info().rss / (1024 * 1024)

        async def run_batch(num_concurrency: int):
            loop = asyncio.get_running_loop()
            queries = [
                UNIQUE_QUERIES[i % len(UNIQUE_QUERIES)] for i in range(num_concurrency)
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
                        use_cache=False,  # Bypass cache to test raw store
                    ),
                )
                dur = (time.perf_counter() - t_start) * 1000.0
                return dur, res[1]

            t_total_start = time.perf_counter()
            batch_res = await asyncio.gather(*(single_worker(q) for q in queries))
            total_wall_s = time.perf_counter() - t_total_start
            return batch_res, total_wall_s

        batch_results, wall_s = asyncio.run(run_batch(c))
        durations = [r[0] for r in batch_results]
        chroma_durations = [r[1].get("search_ms", 0.0) for r in batch_results]
        embed_durations = [r[1].get("embed_ms", 0.0) for r in batch_results]

        mem_end_mb = process.memory_info().rss / (1024 * 1024)
        cpu_util = process.cpu_percent(interval=None)

        results[str(c)] = {
            "concurrency": c,
            "total_requests": c,
            "throughput_rps": round(c / wall_s, 2) if wall_s > 0 else 0.0,
            "p50_latency_ms": round(float(np.percentile(durations, 50)), 2),
            "p95_latency_ms": round(float(np.percentile(durations, 95)), 2),
            "p99_latency_ms": round(float(np.percentile(durations, 99)), 2),
            "max_latency_ms": round(float(np.max(durations)), 2),
            "chroma_search_p50_ms": round(
                float(np.percentile(chroma_durations, 50)), 2
            ),
            "chroma_search_p95_ms": round(
                float(np.percentile(chroma_durations, 95)), 2
            ),
            "embed_p50_ms": round(float(np.percentile(embed_durations, 50)), 2),
            "cpu_percent": round(cpu_util, 1),
            "ram_rss_mb": round(mem_end_mb, 1),
            "ram_growth_mb": round(max(0.0, mem_end_mb - mem_start_mb), 2),
            "active_threads": threading.active_count(),
        }

        logger.info(
            "  Concurrency %3d: Throughput=%6.1f rps | p50=%7.1f ms | p95=%7.1f ms | Chroma p50=%6.1f ms | RAM=%.1fMB",
            c,
            results[str(c)]["throughput_rps"],
            results[str(c)]["p50_latency_ms"],
            results[str(c)]["p95_latency_ms"],
            results[str(c)]["chroma_search_p50_ms"],
            results[str(c)]["ram_rss_mb"],
        )

    return results


# ==============================================================================
# PHASE 3: WORKER ISOLATION TEST (1, 2, 4, 6, 8 WORKERS)
# ==============================================================================
async def wait_for_server(url: str, timeout: float = 50.0) -> bool:
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


def start_worker_server(port: int, workers: int, mock_port: int) -> subprocess.Popen:
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    env = os.environ.copy()
    env["APP_ENV"] = "production"
    env["API_KEY"] = DEFAULT_BENCHMARK_KEY
    env["ALLOWED_HOSTS"] = json.dumps(["127.0.0.1", "localhost", "testserver"])
    env["API_SERVER_PORT"] = str(port)
    env["RATE_LIMIT_PER_MINUTE"] = "100000"
    env["LLM_PROVIDER"] = "deepseek"
    env["DEEPSEEK_BASE_URL"] = f"http://127.0.0.1:{mock_port}/v1"
    env["DEEPSEEK_API_KEY"] = "mock-key-investigation"
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

    return subprocess.Popen(
        cmd, env=env, cwd=root_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


async def run_phase3_worker_isolation_matrix() -> Dict[str, Any]:
    logger.info(
        "======================================================================"
    )
    logger.info("PHASE 3: WORKER ISOLATION MATRIX (1, 2, 4, 6, 8 WORKERS)")
    logger.info(
        "======================================================================"
    )

    port = 8000
    mock_port = 8999
    host = f"http://127.0.0.1:{port}"
    api_key = DEFAULT_BENCHMARK_KEY

    mock_server = MockProviderServer(port=mock_port)
    await mock_server.start()

    worker_counts = [1, 2, 4, 6, 8]
    concurrency_levels = [25, 50, 75, 100]
    matrix_results = {}

    try:
        for w in worker_counts:
            logger.info(
                "----------------------------------------------------------------------"
            )
            logger.info("TESTING WORKER COUNT: %d WORKERS", w)
            logger.info(
                "----------------------------------------------------------------------"
            )

            aria_proc = start_worker_server(port=port, workers=w, mock_port=mock_port)
            is_ready = await wait_for_server(f"{host}/api/v1/health", timeout=60.0)
            if not is_ready:
                logger.error("Failed to start ARIA with %d workers", w)
                try:
                    aria_proc.kill()
                except Exception:
                    pass
                continue

            # Measure parent + child worker processes
            parent_proc = psutil.Process(aria_proc.pid)
            children = parent_proc.children(recursive=True)
            active_pids = [parent_proc.pid] + [c.pid for c in children]

            worker_mem_mb = []
            for p in [parent_proc] + children:
                try:
                    worker_mem_mb.append(p.memory_info().rss / (1024 * 1024))
                except Exception:
                    pass
            total_initial_ram_mb = sum(worker_mem_mb)
            avg_worker_ram_mb = np.mean(worker_mem_mb) if worker_mem_mb else 0.0

            logger.info(
                "  Spawned %d worker processes (Active PIDs: %s) | Total Initial RAM: %.1f MB (Avg/worker: %.1f MB)",
                len(children) if children else 1,
                active_pids,
                total_initial_ram_mb,
                avg_worker_ram_mb,
            )

            worker_sub_results = {}
            engine = BenchmarkEngine(base_url=host, api_key=api_key, timeout=60.0)

            for c in concurrency_levels:
                duration = 18.0 if c <= 50 else 22.0
                res = await engine.run_chat_batch(
                    concurrency=c, duration_s=duration, repo=REPO_NAME
                )

                worker_sub_results[str(c)] = {
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
                }

                logger.info(
                    "    Workers=%d | Concurrency=%3d -> Throughput=%5.2f rps | p50=%7.1fms | p95=%7.1fms | Errors=%.1f%%",
                    w,
                    c,
                    res.throughput_rps,
                    res.p50_latency_ms,
                    res.p95_latency_ms,
                    res.error_rate_pct,
                )

            # Final memory after tests
            final_mem_mb = []
            for p in [parent_proc] + children:
                try:
                    final_mem_mb.append(p.memory_info().rss / (1024 * 1024))
                except Exception:
                    pass

            matrix_results[str(w)] = {
                "workers": w,
                "process_count": len(children) if children else 1,
                "total_initial_ram_mb": round(total_initial_ram_mb, 1),
                "total_final_ram_mb": round(sum(final_mem_mb), 1),
                "avg_worker_ram_mb": round(
                    float(np.mean(final_mem_mb)) if final_mem_mb else 0.0, 1
                ),
                "scaling_data": worker_sub_results,
            }

            try:
                aria_proc.kill()
                for ch in children:
                    try:
                        ch.kill()
                    except Exception:
                        pass
            except Exception:
                pass
            await asyncio.sleep(1.0)

    finally:
        try:
            await mock_server.stop()
        except Exception:
            pass

    return matrix_results


# ==============================================================================
# PHASE 5: READ/WRITE CONTENTION BENCHMARK
# ==============================================================================
def run_phase5_read_write_contention(
    chroma_store: ChromaStore, embedding_service: EmbeddingService
) -> Dict[str, Any]:
    logger.info(
        "======================================================================"
    )
    logger.info("PHASE 5: STORAGE READ/WRITE CONTENTION BENCHMARK")
    logger.info(
        "======================================================================"
    )

    # Isolated dummy test chunks for write tests
    test_file = "services/benchmark_dummy_test_chunk.py"
    dummy_chunks = [
        f"def dummy_function_{i}():\n    return 'chunk_{i}_{uuid.uuid4().hex}'"
        for i in range(10)
    ]
    dummy_embeddings = embedding_service.generate_embeddings_batch(dummy_chunks)
    dummy_metadata = [
        {"repo_name": "benchmark_test_repo", "chunk_id": i} for i in range(10)
    ]

    concurrency = 25
    read_queries = [UNIQUE_QUERIES[i] for i in range(concurrency)]

    # A: READ-ONLY
    t0_read = time.perf_counter()
    read_timings = []
    for q in read_queries:
        t0 = time.perf_counter()
        intelligent_retrieve(
            q, REPO_NAME, embedding_service, chroma_store, use_cache=False
        )
        read_timings.append((time.perf_counter() - t0) * 1000.0)
    wall_read_s = time.perf_counter() - t0_read

    read_only_results = {
        "throughput_rps": round(concurrency / wall_read_s, 2),
        "p50_latency_ms": round(float(np.percentile(read_timings, 50)), 2),
        "p95_latency_ms": round(float(np.percentile(read_timings, 95)), 2),
    }
    logger.info(
        "  [A. Read-Only] Throughput=%5.2f rps | p50=%6.1f ms | p95=%6.1f ms",
        read_only_results["throughput_rps"],
        read_only_results["p50_latency_ms"],
        read_only_results["p95_latency_ms"],
    )

    # B: WRITE-ONLY (10 batch index writes)
    write_timings = []
    t0_write_all = time.perf_counter()
    for i in range(10):
        t0 = time.perf_counter()
        chroma_store.add_code_chunks(
            file_path=f"{test_file}_{i}",
            chunks=dummy_chunks,
            embeddings=dummy_embeddings,
            metadata=dummy_metadata,
        )
        write_timings.append((time.perf_counter() - t0) * 1000.0)
    wall_write_s = time.perf_counter() - t0_write_all

    write_only_results = {
        "throughput_wps": round(10.0 / wall_write_s, 2),
        "p50_latency_ms": round(float(np.percentile(write_timings, 50)), 2),
        "p95_latency_ms": round(float(np.percentile(write_timings, 95)), 2),
    }
    logger.info(
        "  [B. Write-Only] Throughput=%5.2f wps | p50=%6.1f ms | p95=%6.1f ms",
        write_only_results["throughput_wps"],
        write_only_results["p50_latency_ms"],
        write_only_results["p95_latency_ms"],
    )

    # C: MIXED (80% Read / 20% Write Concurrently)
    async def run_mixed_workload():
        loop = asyncio.get_running_loop()
        mixed_read_durs = []
        mixed_write_durs = []

        async def worker_read(q_str: str):
            t0 = time.perf_counter()
            await loop.run_in_executor(
                None,
                lambda: intelligent_retrieve(
                    q_str, REPO_NAME, embedding_service, chroma_store, use_cache=False
                ),
            )
            mixed_read_durs.append((time.perf_counter() - t0) * 1000.0)

        async def worker_write(file_id: int):
            t0 = time.perf_counter()
            await loop.run_in_executor(
                None,
                lambda: chroma_store.add_code_chunks(
                    file_path=f"{test_file}_mixed_{file_id}",
                    chunks=dummy_chunks,
                    embeddings=dummy_embeddings,
                    metadata=dummy_metadata,
                ),
            )
            mixed_write_durs.append((time.perf_counter() - t0) * 1000.0)

        tasks = []
        for idx in range(25):
            if idx % 5 == 0:
                tasks.append(worker_write(idx))
            else:
                tasks.append(worker_read(read_queries[idx]))

        t_total_start = time.perf_counter()
        await asyncio.gather(*tasks)
        tot_wall_s = time.perf_counter() - t_total_start
        return mixed_read_durs, mixed_write_durs, tot_wall_s

    mixed_reads, mixed_writes, mixed_wall_s = asyncio.run(run_mixed_workload())

    mixed_results = {
        "total_throughput_ops": round(25.0 / mixed_wall_s, 2),
        "read_p50_latency_ms": round(float(np.percentile(mixed_reads, 50)), 2),
        "read_p95_latency_ms": round(float(np.percentile(mixed_reads, 95)), 2),
        "write_p50_latency_ms": round(float(np.percentile(mixed_writes, 50)), 2),
        "read_degradation_pct": round(
            (
                (
                    float(np.percentile(mixed_reads, 50))
                    - read_only_results["p50_latency_ms"]
                )
                / read_only_results["p50_latency_ms"]
            )
            * 100.0,
            1,
        ),
    }

    logger.info(
        "  [C. Mixed 80/20] Read p50=%6.1f ms (Degradation vs Read-Only: +%.1f%%) | Write p50=%6.1f ms",
        mixed_results["read_p50_latency_ms"],
        mixed_results["read_degradation_pct"],
        mixed_results["write_p50_latency_ms"],
    )

    # Clean up dummy test files
    try:
        chroma_store.delete_repository("benchmark_test_repo")
    except Exception:
        pass

    return {
        "read_only": read_only_results,
        "write_only": write_only_results,
        "mixed_80_20": mixed_results,
    }


# ==============================================================================
# PHASE 6: CACHE ATTRIBUTION 4-QUADRANT MATRIX
# ==============================================================================
def run_phase6_cache_attribution(
    chroma_store: ChromaStore, embedding_service: EmbeddingService
) -> Dict[str, Any]:
    logger.info(
        "======================================================================"
    )
    logger.info("PHASE 6: CACHE ATTRIBUTION 4-QUADRANT MATRIX")
    logger.info(
        "======================================================================"
    )

    concurrency = 25
    matrix = {}

    def execute_batch(queries_list: List[str], use_lru: bool) -> Dict[str, Any]:
        t0 = time.perf_counter()
        timings = []
        hits = 0
        for q in queries_list:
            t_req = time.perf_counter()
            _, m = intelligent_retrieve(
                question=q,
                repo_name=REPO_NAME,
                embedding_service=embedding_service,
                chroma_store=chroma_store,
                use_cache=use_lru,
            )
            timings.append((time.perf_counter() - t_req) * 1000.0)
            if m.get("cache_hit", False):
                hits += 1
        wall_s = time.perf_counter() - t0
        return {
            "throughput_rps": round(len(queries_list) / wall_s, 2),
            "p50_latency_ms": round(float(np.percentile(timings, 50)), 2),
            "p95_latency_ms": round(float(np.percentile(timings, 95)), 2),
            "avg_latency_ms": round(float(np.mean(timings)), 2),
            "hit_rate_pct": round((hits / len(queries_list)) * 100.0, 1),
        }

    # 1. LRU ENABLED + REPEATED QUERIES
    retrieval_cache.invalidate_all()
    # Prewarm
    for q in REPEATED_QUERIES:
        intelligent_retrieve(
            q, REPO_NAME, embedding_service, chroma_store, use_cache=True
        )
    rep_batch = [
        REPEATED_QUERIES[i % len(REPEATED_QUERIES)] for i in range(concurrency)
    ]
    matrix["lru_enabled_repeated"] = execute_batch(rep_batch, use_lru=True)

    # 2. LRU ENABLED + UNIQUE QUERIES
    retrieval_cache.invalidate_all()
    uniq_batch = [UNIQUE_QUERIES[i] for i in range(concurrency)]
    matrix["lru_enabled_unique"] = execute_batch(uniq_batch, use_lru=True)

    # 3. LRU DISABLED + REPEATED QUERIES
    retrieval_cache.invalidate_all()
    matrix["lru_disabled_repeated"] = execute_batch(rep_batch, use_lru=False)

    # 4. LRU DISABLED + UNIQUE QUERIES
    retrieval_cache.invalidate_all()
    matrix["lru_disabled_unique"] = execute_batch(uniq_batch, use_lru=False)

    logger.info(
        "  Quadrant A (LRU On  + Repeated): Throughput=%7.1f rps | p50=%6.2f ms | Hit Rate=%.1f%%",
        matrix["lru_enabled_repeated"]["throughput_rps"],
        matrix["lru_enabled_repeated"]["p50_latency_ms"],
        matrix["lru_enabled_repeated"]["hit_rate_pct"],
    )
    logger.info(
        "  Quadrant B (LRU On  + Unique):   Throughput=%7.1f rps | p50=%6.2f ms | Hit Rate=%.1f%%",
        matrix["lru_enabled_unique"]["throughput_rps"],
        matrix["lru_enabled_unique"]["p50_latency_ms"],
        matrix["lru_enabled_unique"]["hit_rate_pct"],
    )
    logger.info(
        "  Quadrant C (LRU Off + Repeated): Throughput=%7.1f rps | p50=%6.2f ms | Hit Rate=%.1f%%",
        matrix["lru_disabled_repeated"]["throughput_rps"],
        matrix["lru_disabled_repeated"]["p50_latency_ms"],
        matrix["lru_disabled_repeated"]["hit_rate_pct"],
    )
    logger.info(
        "  Quadrant D (LRU Off + Unique):   Throughput=%7.1f rps | p50=%6.2f ms | Hit Rate=%.1f%%",
        matrix["lru_disabled_unique"]["throughput_rps"],
        matrix["lru_disabled_unique"]["p50_latency_ms"],
        matrix["lru_disabled_unique"]["hit_rate_pct"],
    )

    return matrix


# ==============================================================================
# MAIN RUNNER
# ==============================================================================
def main():
    logger.info(
        "======================================================================"
    )
    logger.info("STARTING ARIA PHASE 2B VECTOR RETRIEVAL INVESTIGATION")
    logger.info(
        "======================================================================"
    )

    chroma_store = ChromaStore(persist_directory=settings.chroma_db_path)
    embedding_service = EmbeddingService()

    phase1_trace = run_phase1_retrieval_path_trace(chroma_store, embedding_service)
    phase2_contention = run_phase2_unique_query_contention(
        chroma_store, embedding_service
    )
    phase3_workers = asyncio.run(run_phase3_worker_isolation_matrix())
    phase5_rw = run_phase5_read_write_contention(chroma_store, embedding_service)
    phase6_cache = run_phase6_cache_attribution(chroma_store, embedding_service)

    final_report_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "hardware": {
            "cpu_count_physical": psutil.cpu_count(logical=False),
            "cpu_count_logical": psutil.cpu_count(logical=True),
            "total_ram_gb": round(psutil.virtual_memory().total / (1024**3), 2),
        },
        "phase1_retrieval_path_trace": phase1_trace,
        "phase2_unique_query_contention": phase2_contention,
        "phase3_worker_isolation_matrix": phase3_workers,
        "phase5_read_write_contention": phase5_rw,
        "phase6_cache_attribution_matrix": phase6_cache,
    }

    output_path = "docs/performance/vector_retrieval_investigation_results.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_report_data, f, indent=2)

    logger.info(
        "======================================================================"
    )
    logger.info("INVESTIGATION COMPLETE - SAVED RAW RESULTS TO %s", output_path)
    logger.info(
        "======================================================================"
    )


if __name__ == "__main__":
    main()
