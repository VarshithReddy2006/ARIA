"""Retrieval Substage Performance Benchmark.

Measures precise timings for:
- Deterministic Detection
- Symbol Lookup
- Query Embedding + Vector Retrieval
- Reranking + Tier Weighting + Classification
- Symbol/Line Metadata Population
- Context Assembly + Budget Enforcement
- Warm Cache Retrieval
"""

import os
import sys
import time

# Ensure root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from services.embedding_service import EmbeddingService
from memory.chroma_store import ChromaStore
from services.chat.retrieval import intelligent_retrieve, detect_deterministic_retrieval
from services.chat.context_builder import ContextBuilder
from services.chat.retrieval_cache import retrieval_cache
from services.symbol_service import SymbolService

REPO_NAME = "VarshithReddy2006/Repo-Intelligence-Agent"

BENCHMARK_QUERIES = [
    ("Deterministic File Query", "Explain backend/api.py routing"),
    ("Deterministic Symbol Query", "Where is the ContextBuilder class defined?"),
    (
        "Semantic QA Query",
        "How does token budgeting and circuit breaker work in the chat pipeline?",
    ),
]


def main():
    print("=" * 70)
    print("ARIA RETRIEVAL PIPELINE PERFORMANCE BENCHMARK")
    print("=" * 70)

    # Initialize services
    print("Initializing services...")
    chroma_store = ChromaStore(persist_directory="data/chroma_db")
    embedding_service = EmbeddingService()
    symbol_service = SymbolService()
    context_builder = ContextBuilder()

    results = []

    for label, query in BENCHMARK_QUERIES:
        print(f"\n--- Testing: {label} ---")
        print(f'Query: "{query}"')

        # 1. Cold Run (cache invalidated)
        retrieval_cache.invalidate_all()

        t0 = time.perf_counter()
        # Test deterministic detection
        det_match = detect_deterministic_retrieval(
            question=query,
            repo_name=REPO_NAME,
            chroma_store=chroma_store,
            symbol_service=symbol_service,
        )
        det_time_ms = (time.perf_counter() - t0) * 1000

        t1 = time.perf_counter()
        chunks, metrics = intelligent_retrieve(
            question=query,
            repo_name=REPO_NAME,
            embedding_service=embedding_service,
            chroma_store=chroma_store,
            symbol_service=symbol_service,
            deterministic_match=det_match,
        )
        retrieve_time_ms = (time.perf_counter() - t1) * 1000

        t2 = time.perf_counter()
        ctx = context_builder.build(
            repo_name=REPO_NAME,
            question=query,
            code_chunks=chunks,
            deterministic_file_path=metrics.get("matched_file")
            if metrics.get("deterministic")
            else None,
        )
        context_build_ms = (time.perf_counter() - t2) * 1000

        cold_total_ms = det_time_ms + retrieve_time_ms + context_build_ms

        # 2. Warm Run (retrieval cache hit)
        t_warm_start = time.perf_counter()
        warm_chunks, warm_metrics = intelligent_retrieve(
            question=query,
            repo_name=REPO_NAME,
            embedding_service=embedding_service,
            chroma_store=chroma_store,
            symbol_service=symbol_service,
            deterministic_match=det_match,
        )
        t_warm_ctx = time.perf_counter()
        _warm_ctx = context_builder.build(
            repo_name=REPO_NAME,
            question=query,
            code_chunks=warm_chunks,
            deterministic_file_path=warm_metrics.get("matched_file")
            if warm_metrics.get("deterministic")
            else None,
        )
        warm_ctx_ms = (time.perf_counter() - t_warm_ctx) * 1000
        warm_total_ms = (time.perf_counter() - t_warm_start) * 1000

        print(f"  [Cold] Deterministic Detection: {det_time_ms:.2f} ms")
        print(f"  [Cold] Retrieval + Ranking:     {retrieve_time_ms:.2f} ms")
        print(f"  [Cold] Context Assembly:        {context_build_ms:.2f} ms")
        print(f"  [Cold] Total Non-LLM Time:      {cold_total_ms:.2f} ms")
        print(
            f"  [Cold] Returned Chunks:         {len(chunks)} ({ctx.estimated_tokens} tokens)"
        )
        print(f"  [Warm] Context Assembly:        {warm_ctx_ms:.2f} ms")
        print(
            f"  [Warm] Total Non-LLM Time:      {warm_total_ms:.2f} ms (Cache Hit: {warm_metrics.get('cache_hit')})"
        )

        substages = metrics.get("substage_profile", {})
        if substages:
            print("  Substage Profile:")
            for sname, sinfo in substages.items():
                print(f"    - {sname:25s}: {sinfo['total_ms']:.2f} ms")

        results.append(
            {
                "label": label,
                "cold_total_ms": cold_total_ms,
                "retrieve_ms": retrieve_time_ms,
                "context_build_ms": context_build_ms,
                "warm_context_build_ms": warm_ctx_ms,
                "warm_total_ms": warm_total_ms,
                "chunks": len(chunks),
                "tokens": ctx.estimated_tokens,
            }
        )

    print("\n" + "=" * 70)
    print("BENCHMARK SUMMARY")
    print("=" * 70)
    print(
        f"{'Query Type':30s} | {'Cold (ms)':10s} | {'Warm (ms)':10s} | {'Chunks':6s} | {'Tokens':6s}"
    )
    print("-" * 70)
    for r in results:
        print(
            f"{r['label']:30s} | {r['cold_total_ms']:9.1f}ms | {r['warm_total_ms']:9.1f}ms | {r['chunks']:6d} | {r['tokens']:6d}"
        )
    print("=" * 70)


if __name__ == "__main__":
    main()
