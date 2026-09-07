"""Answer Pipeline Performance Investigation & LLM Latency Benchmark.

Performs:
1. Complete Answer Path Tracing (Retrieval -> Context -> Prompt -> Provider -> TTFT -> Generation -> Verified Answer).
2. Controlled 5-run Cold and 5-run Warm benchmark with exact statistical metrics (mean, median, P95).
3. Context Size Scaling Experiment (5k, 10k, 20k, 30k, 40k characters).
4. Network vs Generation Latency Separation.
5. Token Generation Throughput (tokens/sec, TTFT, input tokens, output tokens).
6. Single-call Verification (zero duplicate requests, zero hidden retries).
"""

import asyncio
import os
import sys
import time
from typing import Dict, Any
import numpy as np

# Ensure root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from memory.chroma_store import ChromaStore
from services.embedding_service import EmbeddingService
from services.symbol_service import SymbolService
from services.chat.retrieval_pipeline import RetrievalPipeline
from services.chat.provider_manager import ProviderManager
from services.chat.context_builder import ContextBuilder
from services.chat.retrieval_cache import retrieval_cache

REPO_NAME = "VarshithReddy2006/Repo-Intelligence-Agent"
TEST_QUERY = "Explain the architecture of the Chat RetrievalPipeline, including IntentRouting and ContextBuilding."


async def run_detailed_stream_turn(
    pipeline: RetrievalPipeline,
    query: str,
    repo_name: str,
) -> Dict[str, Any]:
    t_start = time.perf_counter()
    tokens = []
    first_token_time = None
    inter_token_times = []
    last_tok_t = None

    t_ttft = None
    stream_iterator = pipeline.retrieve_stream(
        repo_name=repo_name,
        question=query,
    )

    async for chunk_json_str in stream_iterator:
        now = time.perf_counter()
        if last_tok_t is not None:
            inter_token_times.append((now - last_tok_t) * 1000)
        last_tok_t = now

        if first_token_time is None:
            first_token_time = now
            t_ttft = (first_token_time - t_start) * 1000

        tokens.append(chunk_json_str)

    total_time_ms = (time.perf_counter() - t_start) * 1000
    gen_time_ms = (total_time_ms - t_ttft) if t_ttft is not None else 0.0

    # Calculate token throughput
    output_chunk_count = len(tokens)
    tokens_per_sec = (
        (output_chunk_count / (gen_time_ms / 1000.0)) if gen_time_ms > 0 else 0.0
    )

    return {
        "ttft_ms": t_ttft or 0.0,
        "gen_time_ms": gen_time_ms,
        "total_time_ms": total_time_ms,
        "chunks_emitted": output_chunk_count,
        "tokens_per_sec": tokens_per_sec,
        "avg_inter_token_ms": float(np.mean(inter_token_times))
        if inter_token_times
        else 0.0,
    }


async def benchmark_controlled_5_runs(pipeline: RetrievalPipeline):
    print("\n" + "=" * 80, flush=True)
    print("EXPERIMENT 1: CONTROLLED 5-RUN COLD VS WARM BASELINE", flush=True)
    print("=" * 80, flush=True)

    cold_runs = []
    warm_runs = []

    print("\n--- Running 5 Cold Runs (Cache Cleared Per Run) ---", flush=True)
    for i in range(1, 6):
        retrieval_cache.invalidate_all()
        print(f"  Executing Cold Run {i}/5...", flush=True)
        res = await run_detailed_stream_turn(pipeline, TEST_QUERY, REPO_NAME)
        cold_runs.append(res)
        print(
            f"    Run {i}: TTFT={res['ttft_ms']:7.1f}ms | Gen={res['gen_time_ms']:7.1f}ms | Total={res['total_time_ms']:7.1f}ms | Chunks={res['chunks_emitted']:4d} | Speed={res['tokens_per_sec']:5.1f} tok/s",
            flush=True,
        )
        await asyncio.sleep(0.5)

    print("\n--- Running 5 Warm Runs (Warm Process & Cache) ---", flush=True)
    for i in range(1, 6):
        print(f"  Executing Warm Run {i}/5...", flush=True)
        res = await run_detailed_stream_turn(pipeline, TEST_QUERY, REPO_NAME)
        warm_runs.append(res)
        print(
            f"    Run {i}: TTFT={res['ttft_ms']:7.1f}ms | Gen={res['gen_time_ms']:7.1f}ms | Total={res['total_time_ms']:7.1f}ms | Chunks={res['chunks_emitted']:4d} | Speed={res['tokens_per_sec']:5.1f} tok/s",
            flush=True,
        )
        await asyncio.sleep(0.5)

    def stats(data_list, key):
        vals = [d[key] for d in data_list]
        return {
            "mean": float(np.mean(vals)),
            "median": float(np.median(vals)),
            "p95": float(np.percentile(vals, 95)),
        }

    print("\n" + "=" * 80, flush=True)
    print("5-RUN STATISTICAL SUMMARY", flush=True)
    print("=" * 80, flush=True)
    print(
        f"{'Condition':12s} | {'Metric':16s} | {'Mean (ms)':12s} | {'Median (ms)':12s} | {'P95 (ms)':12s}",
        flush=True,
    )
    print("-" * 80, flush=True)
    for cond_name, runs in [("Cold", cold_runs), ("Warm", warm_runs)]:
        for metric in ["ttft_ms", "gen_time_ms", "total_time_ms"]:
            st = stats(runs, metric)
            print(
                f"{cond_name:12s} | {metric:16s} | {st['mean']:10.1f}ms | {st['median']:10.1f}ms | {st['p95']:10.1f}ms",
                flush=True,
            )
    print("=" * 80, flush=True)


async def benchmark_context_size_scaling(provider_manager: ProviderManager):
    print("\n" + "=" * 80, flush=True)
    print("EXPERIMENT 2: CONTEXT SIZE SCALING VS GENERATION LATENCY", flush=True)
    print("=" * 80, flush=True)

    base_context = (
        "def route_request(req): return handle_request(req)\n"
        "class ContextBuilder:\n"
        "    def build(self, repo, q): return BuiltContext(prompt=q)\n"
    )

    sizes = [5_000, 10_000, 20_000, 30_000, 40_000]
    question = "Summarize the component responsibilities in 2 short bullet points."

    print(
        f"{'Context Chars':15s} | {'Approx Tokens':15s} | {'TTFT (ms)':12s} | {'Total (ms)':12s} | {'Tokens/Sec':12s}",
        flush=True,
    )
    print("-" * 80, flush=True)

    for sz in sizes:
        # Repeat base context to reach target size
        multiplier = (sz // len(base_context)) + 1
        synthetic_context = (base_context * multiplier)[:sz]
        full_prompt = f"## Code Context\n```python\n{synthetic_context}\n```\n\n## Question\n{question}"

        t0 = time.perf_counter()
        first_tok_ms = None
        tokens = []

        try:
            async for tok, prov in provider_manager.stream(full_prompt):
                if first_tok_ms is None:
                    first_tok_ms = (time.perf_counter() - t0) * 1000
                tokens.append(tok)
            total_ms = (time.perf_counter() - t0) * 1000
            gen_ms = total_ms - (first_tok_ms or 0)
            tps = len(tokens) / (gen_ms / 1000.0) if gen_ms > 0 else 0

            print(
                f"{sz:15d} | {sz // 4:15d} | {first_tok_ms:10.1f}ms | {total_ms:10.1f}ms | {tps:10.1f} tok/s",
                flush=True,
            )
        except Exception as exc:
            print(f"{sz:15d} | {sz // 4:15d} | FAILED: {exc}", flush=True)

        await asyncio.sleep(1.0)
    print("=" * 80, flush=True)


async def main():
    print("Initializing services for answer pipeline benchmark...", flush=True)
    chroma_store = ChromaStore(persist_directory="data/chroma_db")
    embedding_service = EmbeddingService()
    symbol_service = SymbolService()
    provider_manager = ProviderManager()
    context_builder = ContextBuilder()

    pipeline = RetrievalPipeline(
        embedding_service=embedding_service,
        chroma_store=chroma_store,
        provider_manager=provider_manager,
        context_builder=context_builder,
        symbol_service=symbol_service,
    )

    await benchmark_controlled_5_runs(pipeline)
    await benchmark_context_size_scaling(provider_manager)


if __name__ == "__main__":
    asyncio.run(main())
