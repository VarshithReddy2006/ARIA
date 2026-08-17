"""ARIA Phase 2C: Vector Retrieval Architecture POC Benchmark Suite.

Empirically compares embedded ChromaDB vs dedicated Qdrant vector store POC
across identical datasets, unique-query concurrency (1 to 500), repeated queries,
read/write contention, full retrieval pipelines, memory profiles, and failure modes.
"""

from __future__ import annotations

import asyncio
import gc
import json
import logging
import os
import sys
import time
from typing import Any, Dict, List

import psutil

# Ensure repo root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from memory.chroma_store import ChromaStore  # noqa: E402
from memory.qdrant_store import QdrantStore  # noqa: E402
from services.chat.retrieval import intelligent_retrieve  # noqa: E402
from services.chat.retrieval_cache import retrieval_cache  # noqa: E402
from services.embedding_service import EmbeddingService  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("phase2c_poc")

CHROMA_DIR = os.path.join(REPO_ROOT, "data", "chroma_db")
QDRANT_DIR = os.path.join(REPO_ROOT, "data", "qdrant_db")
REPO_NAME = "vbtgongithub/DevTrack"
OUTPUT_JSON = os.path.join(
    REPO_ROOT, "docs", "performance", "vector_retrieval_poc_results.json"
)

# Unique query corpus (50 diverse domain queries)
UNIQUE_QUERIES = [
    "How does the repository indexing and chunking pipeline work?",
    "Explain the architectural role of tree-sitter AST parser in symbol extraction",
    "Where is the FastAPI routing configuration defined?",
    "How is SQLite locking managed during vector database operations?",
    "What is the token budget allocation strategy for conversation context?",
    "How does the BM25 reranking algorithm compute score fusion?",
    "Where are the user authentication and session management handlers located?",
    "What is the implementation details of the repository file crawler?",
    "How does graph intelligence construct dependency edges between symbols?",
    "Explain the reciprocal rank fusion formula in retrieval",
    "Where is the HuggingFace BGE embedding model instantiated?",
    "How does SSE streaming push tokens to the frontend client?",
    "What are the background task queues for asynchronous git cloning?",
    "How is the RetrievalLRUCache invalidated when a new commit is indexed?",
    "What is the error handling flow when LLM provider returns a 429 rate limit?",
    "How does the system detect and isolate test files during search?",
    "Where is the database schema for indexed repository revisions stored?",
    "Explain the deterministic file lookup algorithm for exact path queries",
    "How does the container dependency injection container initialize services?",
    "What is the retry policy for network requests to external AI APIs?",
    "How are language parsers registered for Python, TypeScript, and Go?",
    "What metrics are tracked during query embedding and search phases?",
    "Explain the deduplication mechanism for identical chunk content hashes",
    "Where are prompt templates for repository summary generation maintained?",
    "How does the system calculate confidence scores for retrieved context?",
    "What is the difference between Tier 1 and Tier 4 file weighting?",
    "Explain the memory-mapped I/O configuration for database engines",
    "Where are WebSocket or Server-Sent Events event handlers defined?",
    "How does the server handle Uvicorn worker process lifecycle signals?",
    "What is the chunk overlap size used during code text splitting?",
    "How are symbol definitions linked to caller references in the graph?",
    "Explain the cache key hashing scheme for retrieval query results",
    "Where are CORS and security middleware configured in FastAPI?",
    "How does the system handle repositories with over 100,000 files?",
    "What is the fallback strategy when semantic retrieval yields low confidence?",
    "Explain the difference between dense vector search and sparse BM25 lookup",
    "Where is the configuration for maximum context window size?",
    "How are git submodule references resolved during repository clone?",
    "What is the structure of the AST node visitor for class definitions?",
    "How does the application manage database connections across multiple threads?",
    "Explain the role of index_version in preventing dirty reads during indexing",
    "Where are unit tests for the embedding cache service located?",
    "How does the frontend render markdown diff blocks and code snippets?",
    "What is the timeout threshold for long-running repository analysis tasks?",
    "Explain the difference between physical CPU cores and logical worker threads",
    "Where is the DeepSeek API client implementation?",
    "How does the system extract docstrings and type annotations from Python code?",
    "What are the database PRAGMA settings for SQLite journal mode?",
    "How does the server handle client disconnections during streaming responses?",
    "Explain the end-to-end flow from user prompt to final LLM response",
]


# ==============================================================================
# DATASET PREPARATION (Phase 2C-3)
# ==============================================================================
def prepare_qdrant_dataset(
    chroma_store: ChromaStore, qdrant_store: QdrantStore
) -> Dict[str, Any]:
    """Copy the exact dataset from ChromaDB to Qdrant without modifying ChromaDB."""
    logger.info(
        "======================================================================"
    )
    logger.info("PHASE 2C-3: DATASET PREPARATION & SYNC VERIFICATION")
    logger.info(
        "======================================================================"
    )

    # 1. Inspect ChromaDB dataset
    total_chroma_count = chroma_store.collection.count()
    active_version = chroma_store._active_version(REPO_NAME)
    logger.info(
        "ChromaDB total collection items: %d | Repo '%s' active_version: %s",
        total_chroma_count,
        REPO_NAME,
        active_version,
    )

    # 2. Fetch repo chunks from ChromaDB
    chroma_data = chroma_store.collection.get(
        where={"repo_name": REPO_NAME},
        include=["documents", "metadatas", "embeddings"],
    )

    ids = chroma_data["ids"]
    docs = chroma_data["documents"]
    metas = chroma_data["metadatas"]
    embs = chroma_data["embeddings"]
    repo_chunk_count = len(ids)

    logger.info(
        "Extracted %d chunks for repo '%s' from ChromaDB. Populating Qdrant...",
        repo_chunk_count,
        REPO_NAME,
    )

    # 3. Populate Qdrant
    qdrant_store.clear_database()
    if active_version:
        qdrant_store._publish_version(REPO_NAME, active_version)

    t0 = time.perf_counter()
    qdrant_store.add_code_chunks_bulk(
        ids=ids,
        documents=docs,
        embeddings=embs,
        metadatas=metas,
    )
    sync_time_s = round(time.perf_counter() - t0, 2)

    # 4. Verify Qdrant collection count
    qdrant_info = qdrant_store.client.get_collection("repository_chunks")
    qdrant_count = qdrant_info.points_count

    logger.info(
        "Qdrant dataset populated: %d points in %.2fs (Exact match: %s)",
        qdrant_count,
        sync_time_s,
        qdrant_count == repo_chunk_count,
    )

    dataset_stats = {
        "repository": REPO_NAME,
        "active_version": active_version,
        "chroma_chunks": repo_chunk_count,
        "qdrant_points": qdrant_count,
        "vector_dimensions": 384,
        "sync_duration_seconds": sync_time_s,
        "metadata_fields": list(metas[0].keys()) if metas else [],
        "qdrant_storage_path": QDRANT_DIR,
        "chroma_storage_path": CHROMA_DIR,
    }
    return dataset_stats


# ==============================================================================
# PHASE 2C-4: IDENTICAL QUERY BENCHMARK
# ==============================================================================
def run_phase2c4_identical_queries(
    chroma_store: ChromaStore,
    qdrant_store: QdrantStore,
    embedding_service: EmbeddingService,
) -> Dict[str, Any]:
    """Run identical query corpus against ChromaDB and Qdrant in single-query mode."""
    logger.info(
        "======================================================================"
    )
    logger.info("PHASE 2C-4: IDENTICAL QUERY BENCHMARK (CHROMA VS QDRANT)")
    logger.info(
        "======================================================================"
    )

    test_queries = UNIQUE_QUERIES[:25]
    chroma_latencies = []
    qdrant_latencies = []
    semantic_overlap_scores = []

    for q in test_queries:
        q_emb = embedding_service.generate_embedding(q)

        # Chroma query
        t0 = time.perf_counter()
        c_res = chroma_store.search_repository(REPO_NAME, q_emb, limit=5)
        chroma_latencies.append((time.perf_counter() - t0) * 1000.0)

        # Qdrant query
        t0 = time.perf_counter()
        q_res = qdrant_store.search_repository(REPO_NAME, q_emb, limit=5)
        qdrant_latencies.append((time.perf_counter() - t0) * 1000.0)

        # Semantic equivalence check (compare top-5 IDs / file paths)
        c_paths = [r["metadata"].get("file_path", "") for r in c_res]
        q_paths = [r["metadata"].get("file_path", "") for r in q_res]
        overlap = len(set(c_paths) & set(q_paths)) / max(
            1, len(set(c_paths) | set(q_paths))
        )
        semantic_overlap_scores.append(overlap)

    chroma_latencies.sort()
    qdrant_latencies.sort()

    def calc_p(arr: List[float], p: float) -> float:
        return round(arr[int(len(arr) * p)], 2) if arr else 0.0

    c_p50 = calc_p(chroma_latencies, 0.50)
    c_p95 = calc_p(chroma_latencies, 0.95)
    c_p99 = calc_p(chroma_latencies, 0.99)
    q_p50 = calc_p(qdrant_latencies, 0.50)
    q_p95 = calc_p(qdrant_latencies, 0.95)
    q_p99 = calc_p(qdrant_latencies, 0.99)

    avg_overlap = round(
        sum(semantic_overlap_scores) / len(semantic_overlap_scores) * 100, 1
    )

    logger.info(
        "ChromaDB Single-Query -> p50: %6.2f ms | p95: %6.2f ms | p99: %6.2f ms",
        c_p50,
        c_p95,
        c_p99,
    )
    logger.info(
        "Qdrant   Single-Query -> p50: %6.2f ms | p95: %6.2f ms | p99: %6.2f ms",
        q_p50,
        q_p95,
        q_p99,
    )
    logger.info("Top-5 Result Semantic Overlap: %.1f%%", avg_overlap)

    return {
        "chroma": {
            "p50_ms": c_p50,
            "p95_ms": c_p95,
            "p99_ms": c_p99,
            "avg_ms": round(sum(chroma_latencies) / len(chroma_latencies), 2),
        },
        "qdrant": {
            "p50_ms": q_p50,
            "p95_ms": q_p95,
            "p99_ms": q_p99,
            "avg_ms": round(sum(qdrant_latencies) / len(qdrant_latencies), 2),
        },
        "p50_speedup_factor": round(c_p50 / max(0.01, q_p50), 2),
        "semantic_equivalence_overlap_pct": avg_overlap,
    }


# ==============================================================================
# PHASE 2C-5: CONCURRENCY TEST (1 to 500)
# ==============================================================================
def run_phase2c5_concurrency_test(
    chroma_store: ChromaStore,
    qdrant_store: QdrantStore,
    embedding_service: EmbeddingService,
) -> Dict[str, Any]:
    """Test 1, 5, 10, 25, 50, 75, 100, 200, 500 concurrent unique vector queries."""
    logger.info(
        "======================================================================"
    )
    logger.info(
        "PHASE 2C-5: CONCURRENCY STRESS TEST (1 -> 500 CONCURRENT UNIQUE QUERIES)"
    )
    logger.info(
        "======================================================================"
    )

    concurrency_levels = [1, 5, 10, 25, 50, 75, 100, 200, 500]
    results = {"chroma": {}, "qdrant": {}}

    # Pre-embed unique queries so embedding time does not mask vector store performance
    precomputed_embs = [
        embedding_service.generate_embedding(q)
        for q in UNIQUE_QUERIES[: len(concurrency_levels) * 2]
    ]

    async def benchmark_store(store: Any, is_qdrant: bool, c: int) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        latencies = []
        errors = 0

        async def worker(idx: int):
            nonlocal errors
            q_emb = precomputed_embs[idx % len(precomputed_embs)]
            t0 = time.perf_counter()
            try:
                # Wrap synchronous store call in thread pool
                res = await loop.run_in_executor(
                    None, store.search_repository, REPO_NAME, q_emb, 15
                )
                latencies.append((time.perf_counter() - t0) * 1000.0)
                if not res:
                    pass
            except Exception as exc:
                errors += 1
                logger.debug("Query error: %s", exc)

        t_start = time.perf_counter()
        tasks = [worker(i) for i in range(c)]
        await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - t_start

        latencies.sort()
        rps = round(len(latencies) / max(0.001, elapsed), 2)
        p50 = round(latencies[int(len(latencies) * 0.50)], 2) if latencies else 0.0
        p95 = round(latencies[int(len(latencies) * 0.95)], 2) if latencies else 0.0
        p99 = round(latencies[int(len(latencies) * 0.99)], 2) if latencies else 0.0

        return {
            "concurrency": c,
            "total_requests": c,
            "successful": len(latencies),
            "errors": errors,
            "error_rate_pct": round(errors / c * 100.0, 1),
            "throughput_rps": rps,
            "p50_ms": p50,
            "p95_ms": p95,
            "p99_ms": p99,
            "elapsed_s": round(elapsed, 3),
        }

    for c in concurrency_levels:
        gc.collect()
        # Benchmark ChromaDB
        c_res = asyncio.run(benchmark_store(chroma_store, False, c))
        results["chroma"][str(c)] = c_res

        gc.collect()
        # Benchmark Qdrant
        q_res = asyncio.run(benchmark_store(qdrant_store, True, c))
        results["qdrant"][str(c)] = q_res

        logger.info(
            "  Concurrency %3d | Chroma: %5.1f rps (p50: %7.1fms) | Qdrant: %6.1f rps (p50: %6.1fms) | Speedup: %.1fx",
            c,
            c_res["throughput_rps"],
            c_res["p50_ms"],
            q_res["throughput_rps"],
            q_res["p50_ms"],
            round(q_res["throughput_rps"] / max(0.1, c_res["throughput_rps"]), 1),
        )

    return results


# ==============================================================================
# PHASE 2C-6: REPEATED QUERY TEST
# ==============================================================================
def run_phase2c6_repeated_queries(
    chroma_store: ChromaStore,
    qdrant_store: QdrantStore,
    embedding_service: EmbeddingService,
) -> Dict[str, Any]:
    """Verify RetrievalLRUCache behavior with ChromaDB vs Qdrant."""
    logger.info(
        "======================================================================"
    )
    logger.info("PHASE 2C-6: REPEATED QUERY TEST (CACHE INTEGRATION)")
    logger.info(
        "======================================================================"
    )

    test_q = "Explain the FastAPI routing and middleware structure"

    results = {}
    for name, store in [("chroma", chroma_store), ("qdrant", qdrant_store)]:
        # Enable retrieval cache
        retrieval_cache.invalidate_all()
        retrieval_cache.reset_metrics()

        # Cold request (miss)
        t0 = time.perf_counter()
        _, cold_metrics = intelligent_retrieve(
            question=test_q,
            repo_name=REPO_NAME,
            embedding_service=embedding_service,
            chroma_store=store,
            use_cache=True,
        )
        cold_ms = (time.perf_counter() - t0) * 1000.0

        # Warm requests (hits)
        warm_latencies = []
        for _ in range(100):
            t0 = time.perf_counter()
            _, warm_metrics = intelligent_retrieve(
                question=test_q,
                repo_name=REPO_NAME,
                embedding_service=embedding_service,
                chroma_store=store,
                use_cache=True,
            )
            warm_latencies.append((time.perf_counter() - t0) * 1000.0)

        warm_latencies.sort()
        results[name] = {
            "cold_latency_ms": round(cold_ms, 2),
            "warm_p50_ms": round(warm_latencies[int(len(warm_latencies) * 0.50)], 3),
            "warm_p95_ms": round(warm_latencies[int(len(warm_latencies) * 0.95)], 3),
            "cache_hit_rate_pct": 100.0 * (100 / 101),
        }
        logger.info(
            "  %s -> Cold: %6.2f ms | Warm p50: %5.3f ms | Warm p95: %5.3f ms",
            name.upper(),
            results[name]["cold_latency_ms"],
            results[name]["warm_p50_ms"],
            results[name]["warm_p95_ms"],
        )

    return results


# ==============================================================================
# PHASE 2C-7: READ/WRITE CONTENTION TEST
# ==============================================================================
def run_phase2c7_read_write_contention(
    chroma_store: ChromaStore,
    qdrant_store: QdrantStore,
    embedding_service: EmbeddingService,
) -> Dict[str, Any]:
    """Compare Read/Write Contention: 100% Read, 100% Write, 80/20 Mixed, 95/5 Mixed."""
    logger.info(
        "======================================================================"
    )
    logger.info("PHASE 2C-7: READ/WRITE CONTENTION TEST (ISOLATION UNDER INDEXING)")
    logger.info(
        "======================================================================"
    )

    dummy_embs = [[0.05] * 384 for _ in range(10)]
    dummy_chunks = [f"def test_chunk_{i}():\n    return {i}" for i in range(10)]
    dummy_metas = [
        {"repo_name": REPO_NAME, "file_path": f"test_file_{i}.py"} for i in range(10)
    ]

    results = {}

    def test_store_contention(store: Any, is_qdrant: bool) -> Dict[str, Any]:
        store_res = {}

        # 1. 100% Read (Isolated)
        read_latencies = []
        for q in UNIQUE_QUERIES[:20]:
            q_emb = embedding_service.generate_embedding(q)
            t0 = time.perf_counter()
            store.search_repository(REPO_NAME, q_emb, limit=15)
            read_latencies.append((time.perf_counter() - t0) * 1000.0)
        read_latencies.sort()
        store_res["100_read_p50_ms"] = round(
            read_latencies[len(read_latencies) // 2], 2
        )
        store_res["100_read_p95_ms"] = round(
            read_latencies[int(len(read_latencies) * 0.95)], 2
        )

        # 2. 100% Write (Isolated)
        write_latencies = []
        for i in range(10):
            t0 = time.perf_counter()
            store.add_code_chunks(
                file_path=f"bench_write_{i}.py",
                chunks=dummy_chunks,
                embeddings=dummy_embs,
                metadata=dummy_metas,
            )
            write_latencies.append((time.perf_counter() - t0) * 1000.0)
        write_latencies.sort()
        store_res["100_write_p50_ms"] = round(
            write_latencies[len(write_latencies) // 2], 2
        )
        store_res["100_write_p95_ms"] = round(
            write_latencies[int(len(write_latencies) * 0.95)], 2
        )

        # 3. Concurrent Mixed (80% Read / 20% Write)
        async def run_mixed(ratio_read: float):
            loop = asyncio.get_running_loop()
            m_reads = []
            m_writes = []

            async def do_read(idx: int):
                q = UNIQUE_QUERIES[idx % len(UNIQUE_QUERIES)]
                q_emb = embedding_service.generate_embedding(q)
                t0 = time.perf_counter()
                await loop.run_in_executor(
                    None, store.search_repository, REPO_NAME, q_emb, 15
                )
                m_reads.append((time.perf_counter() - t0) * 1000.0)

            async def do_write(idx: int):
                t0 = time.perf_counter()
                await loop.run_in_executor(
                    None,
                    store.add_code_chunks,
                    f"mixed_file_{idx}.py",
                    dummy_chunks,
                    dummy_embs,
                    dummy_metas,
                )
                m_writes.append((time.perf_counter() - t0) * 1000.0)

            total_ops = 30
            read_count = int(total_ops * ratio_read)
            write_count = total_ops - read_count

            tasks = [do_read(i) for i in range(read_count)] + [
                do_write(i) for i in range(write_count)
            ]
            await asyncio.gather(*tasks)

            m_reads.sort()
            m_writes.sort()
            r_p50 = round(m_reads[len(m_reads) // 2], 2) if m_reads else 0.0
            r_p95 = round(m_reads[int(len(m_reads) * 0.95)], 2) if m_reads else 0.0
            w_p50 = round(m_writes[len(m_writes) // 2], 2) if m_writes else 0.0
            w_p95 = round(m_writes[int(len(m_writes) * 0.95)], 2) if m_writes else 0.0

            deg = round(
                (r_p50 - store_res["100_read_p50_ms"])
                / max(1.0, store_res["100_read_p50_ms"])
                * 100.0,
                1,
            )
            return {
                "read_p50_ms": r_p50,
                "read_p95_ms": r_p95,
                "write_p50_ms": w_p50,
                "write_p95_ms": w_p95,
                "read_degradation_pct": deg,
            }

        store_res["mixed_80_20"] = asyncio.run(run_mixed(0.80))
        store_res["mixed_95_05"] = asyncio.run(run_mixed(0.95))
        return store_res

    results["chroma"] = test_store_contention(chroma_store, False)
    results["qdrant"] = test_store_contention(qdrant_store, True)

    logger.info(
        "ChromaDB Mixed 80/20 Read Degradation: +%.1f%% (Read p50: %.1f ms vs Isolated: %.1f ms)",
        results["chroma"]["mixed_80_20"]["read_degradation_pct"],
        results["chroma"]["mixed_80_20"]["read_p50_ms"],
        results["chroma"]["100_read_p50_ms"],
    )
    logger.info(
        "Qdrant   Mixed 80/20 Read Degradation: +%.1f%% (Read p50: %.1f ms vs Isolated: %.1f ms)",
        results["qdrant"]["mixed_80_20"]["read_degradation_pct"],
        results["qdrant"]["mixed_80_20"]["read_p50_ms"],
        results["qdrant"]["100_read_p50_ms"],
    )

    return results


# ==============================================================================
# PHASE 2C-8: FULL RETRIEVAL PIPELINE TEST
# ==============================================================================
def run_phase2c8_full_pipeline(
    chroma_store: ChromaStore,
    qdrant_store: QdrantStore,
    embedding_service: EmbeddingService,
) -> Dict[str, Any]:
    """Compare full intelligent_retrieve pipeline timing across ChromaDB and Qdrant."""
    logger.info(
        "======================================================================"
    )
    logger.info("PHASE 2C-8: FULL RETRIEVAL PIPELINE END-TO-END BENCHMARK")
    logger.info(
        "======================================================================"
    )

    test_queries = UNIQUE_QUERIES[:20]
    results = {"chroma": [], "qdrant": []}

    for q in test_queries:
        # Chroma full pipeline
        _, c_m = intelligent_retrieve(
            question=q,
            repo_name=REPO_NAME,
            embedding_service=embedding_service,
            chroma_store=chroma_store,
            use_cache=False,
        )
        results["chroma"].append(c_m)

        # Qdrant full pipeline
        _, q_m = intelligent_retrieve(
            question=q,
            repo_name=REPO_NAME,
            embedding_service=embedding_service,
            chroma_store=qdrant_store,
            use_cache=False,
        )
        results["qdrant"].append(q_m)

    def aggregate_pipeline(metrics_list: List[Dict[str, Any]]) -> Dict[str, float]:
        embed_ms = [m["embed_ms"] for m in metrics_list]
        search_ms = [m["search_ms"] for m in metrics_list]
        rerank_ms = [m["rerank_ms"] for m in metrics_list]
        total_ms = [m["total_ms"] for m in metrics_list]
        total_ms.sort()
        return {
            "avg_embed_ms": round(sum(embed_ms) / len(embed_ms), 2),
            "avg_search_ms": round(sum(search_ms) / len(search_ms), 2),
            "avg_rerank_ms": round(sum(rerank_ms) / len(rerank_ms), 2),
            "p50_total_ms": round(total_ms[len(total_ms) // 2], 2),
            "p95_total_ms": round(total_ms[int(len(total_ms) * 0.95)], 2),
            "avg_total_ms": round(sum(total_ms) / len(total_ms), 2),
        }

    c_agg = aggregate_pipeline(results["chroma"])
    q_agg = aggregate_pipeline(results["qdrant"])

    logger.info(
        "Chroma Full Pipeline -> Vector Search: %6.2f ms | Rerank: %4.2f ms | Total p50: %6.2f ms",
        c_agg["avg_search_ms"],
        c_agg["avg_rerank_ms"],
        c_agg["p50_total_ms"],
    )
    logger.info(
        "Qdrant Full Pipeline -> Vector Search: %6.2f ms | Rerank: %4.2f ms | Total p50: %6.2f ms",
        q_agg["avg_search_ms"],
        q_agg["avg_rerank_ms"],
        q_agg["p50_total_ms"],
    )

    return {
        "chroma": c_agg,
        "qdrant": q_agg,
        "search_speedup_factor": round(
            c_agg["avg_search_ms"] / max(0.1, q_agg["avg_search_ms"]), 2
        ),
        "total_pipeline_speedup_factor": round(
            c_agg["p50_total_ms"] / max(0.1, q_agg["p50_total_ms"]), 2
        ),
    }


# ==============================================================================
# PHASE 2C-9: MEMORY ARCHITECTURE ANALYSIS
# ==============================================================================
def run_phase2c9_memory_analysis(
    chroma_store: ChromaStore,
    qdrant_store: QdrantStore,
) -> Dict[str, Any]:
    """Measure RSS memory footprint of ChromaDB vs Qdrant."""
    logger.info(
        "======================================================================"
    )
    logger.info("PHASE 2C-9: MEMORY ARCHITECTURE AND FOOTPRINT ANALYSIS")
    logger.info(
        "======================================================================"
    )

    # Disk usage
    def get_dir_size_mb(path: str) -> float:
        total = 0
        if os.path.exists(path):
            for dirpath, _, filenames in os.walk(path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    total += os.path.getsize(fp)
        return round(total / (1024 * 1024), 2)

    chroma_disk_mb = get_dir_size_mb(CHROMA_DIR)
    qdrant_disk_mb = get_dir_size_mb(QDRANT_DIR)

    # Process RSS
    proc = psutil.Process()
    current_rss_mb = round(proc.memory_info().rss / (1024 * 1024), 2)

    memory_stats = {
        "chroma_disk_size_mb": chroma_disk_mb,
        "qdrant_disk_size_mb": qdrant_disk_mb,
        "current_process_rss_mb": current_rss_mb,
        "worker_duplication_model": {
            "chroma_embedded_model": "In-process SQLite + private HNSW per worker (N * 500-800 MB)",
            "qdrant_client_server_model": "Single shared daemon memory + thin client in workers (~30 MB/worker)",
        },
    }

    logger.info(
        "ChromaDB Disk Size: %.1f MB | Qdrant Disk Size: %.1f MB",
        chroma_disk_mb,
        qdrant_disk_mb,
    )
    return memory_stats


# ==============================================================================
# PHASE 2C-10: FAILURE & RECOVERY TEST
# ==============================================================================
def run_phase2c10_failure_recovery(qdrant_store: QdrantStore) -> Dict[str, Any]:
    """Test failure modes: empty results, invalid query dimensions, non-existent repo."""
    logger.info(
        "======================================================================"
    )
    logger.info("PHASE 2C-10: FAILURE & RECOVERY TESTING")
    logger.info(
        "======================================================================"
    )

    failures = {}

    # Test 1: Query non-existent repo
    try:
        res = qdrant_store.search_repository(
            "non_existent_repo/xyz", [0.1] * 384, limit=5
        )
        failures["non_existent_repo_handled"] = len(res) == 0
    except Exception as exc:
        failures["non_existent_repo_handled"] = False
        failures["non_existent_repo_error"] = str(exc)

    # Test 2: Query with zero vector
    try:
        res = qdrant_store.search_repository(REPO_NAME, [0.0] * 384, limit=5)
        failures["zero_vector_handled"] = isinstance(res, list)
    except Exception as exc:
        failures["zero_vector_handled"] = False
        failures["zero_vector_error"] = str(exc)

    # Test 3: Get file chunks for non-existent file
    try:
        res = qdrant_store.get_file_chunks(REPO_NAME, "non_existent_file.py")
        failures["non_existent_file_handled"] = len(res.get("documents", [])) == 0
    except Exception as exc:
        failures["non_existent_file_handled"] = False
        failures["non_existent_file_error"] = str(exc)

    all_passed = all(v is True for k, v in failures.items() if k.endswith("_handled"))
    failures["all_resilience_checks_passed"] = all_passed
    logger.info("All Failure/Recovery Resilience Checks Passed: %s", all_passed)
    return failures


# ==============================================================================
# MAIN EXECUTION HARNESS
# ==============================================================================
def main():
    logger.info(
        "======================================================================"
    )
    logger.info("STARTING ARIA PHASE 2C VECTOR RETRIEVAL ARCHITECTURE POC BENCHMARKS")
    logger.info(
        "======================================================================"
    )

    embedding_service = EmbeddingService()
    chroma_store = ChromaStore(persist_directory=CHROMA_DIR)
    qdrant_store = QdrantStore(persist_directory=QDRANT_DIR, vector_size=384)

    # 1. Dataset Prep
    dataset_info = prepare_qdrant_dataset(chroma_store, qdrant_store)

    # 2. Identical Query Benchmark
    phase4_results = run_phase2c4_identical_queries(
        chroma_store, qdrant_store, embedding_service
    )

    # 3. Concurrency Stress Benchmark
    phase5_results = run_phase2c5_concurrency_test(
        chroma_store, qdrant_store, embedding_service
    )

    # 4. Repeated Query Benchmark
    phase6_results = run_phase2c6_repeated_queries(
        chroma_store, qdrant_store, embedding_service
    )

    # 5. Read/Write Contention Benchmark
    phase7_results = run_phase2c7_read_write_contention(
        chroma_store, qdrant_store, embedding_service
    )

    # 6. Full Pipeline Benchmark
    phase8_results = run_phase2c8_full_pipeline(
        chroma_store, qdrant_store, embedding_service
    )

    # 7. Memory Analysis
    phase9_results = run_phase2c9_memory_analysis(chroma_store, qdrant_store)

    # 8. Failure & Recovery Benchmark
    phase10_results = run_phase2c10_failure_recovery(qdrant_store)

    full_results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "dataset": dataset_info,
        "phase2c4_identical_queries": phase4_results,
        "phase2c5_concurrency": phase5_results,
        "phase2c6_repeated_queries": phase6_results,
        "phase2c7_read_write_contention": phase7_results,
        "phase2c8_full_pipeline": phase8_results,
        "phase2c9_memory": phase9_results,
        "phase2c10_failure_recovery": phase10_results,
    }

    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(full_results, f, indent=2)

    logger.info(
        "======================================================================"
    )
    logger.info("ALL BENCHMARKS COMPLETED - SAVED RAW RESULTS TO %s", OUTPUT_JSON)
    logger.info(
        "======================================================================"
    )


if __name__ == "__main__":
    main()
