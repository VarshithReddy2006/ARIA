"""Cold vs Warm vs Incremental Benchmark (Phase 14).

Measures and contrasts:
1. Cold Index Construction: No index exists, test files parsed for first time.
2. Warm Query Latency: TestImpactIndex in-memory, O(1) test lookup.
3. Incremental Update: A single test file is modified/updated in-place without rebuilding.
"""

import os
import sys
import time
import json
import statistics

sys.path.insert(0, os.path.abspath("."))

from backend.dependencies import get_impact_analysis_service
from services.test_impact_index import TestImpactIndex


def run_benchmark():
    tasks_path = os.path.join("evaluation", "tasks", "tasks.json")
    with open(tasks_path, "r", encoding="utf-8") as fp:
        tasks = json.load(fp)

    service = get_impact_analysis_service()

    # Clear all caches for Cold run
    TestImpactIndex.clear_cache()
    if hasattr(service, "_symbol_query_cache"):
        service._symbol_query_cache.clear()
    if hasattr(service, "_file_content_cache"):
        service._file_content_cache.clear()
    if hasattr(service, "_api_surface_cache"):
        service._api_surface_cache.clear()

    cold_latencies = []
    warm_latencies = []
    incremental_latencies = []

    print("=" * 80)
    print("RUNNING COLD vs WARM vs INCREMENTAL BENCHMARK (Phase 14)")
    print("=" * 80)

    # 1. Cold Measurement
    print("\n--- 1. Cold Queries (First encounter, index build) ---")
    for idx, task in enumerate(tasks, start=1):
        repo = task["repository"]
        desc = task["change_description"]
        t0 = time.perf_counter()
        service.analyze_change(repo, desc)
        tot_ms = (time.perf_counter() - t0) * 1000.0
        cold_latencies.append(tot_ms)
        print(f"  [{idx:2d}/10] {task['task_id']:38s}: {tot_ms:7.2f} ms")

    # 2. Warm Measurement
    print("\n--- 2. Warm Queries (Indexed in-memory lookups) ---")
    for idx, task in enumerate(tasks, start=1):
        repo = task["repository"]
        desc = task["change_description"]
        t0 = time.perf_counter()
        service.analyze_change(repo, desc)
        tot_ms = (time.perf_counter() - t0) * 1000.0
        warm_latencies.append(tot_ms)
        print(f"  [{idx:2d}/10] {task['task_id']:38s}: {tot_ms:7.2f} ms")

    # 3. Incremental Update Measurement
    print("\n--- 3. Incremental Updates (1 test file modified) ---")
    # Simulate modifying 1 test file in requests, fastapi, aria
    test_updates = [
        ("psf/requests", "tests/test_requests.py"),
        ("fastapi/fastapi", "tests/test_security_oauth2.py"),
        ("VarshithReddy2006/ARIA", "tests/test_impact_analysis.py"),
    ]

    for repo, tf in test_updates:
        idx_inst = TestImpactIndex.get_index(repo)
        t0 = time.perf_counter()
        idx_inst.update_file_incremental(tf)
        inc_ms = (time.perf_counter() - t0) * 1000.0
        incremental_latencies.append(inc_ms)
        print(f"  Incremental update for {repo} ({tf}): {inc_ms:6.2f} ms")

    # Latency summaries
    cold_mean = statistics.mean(cold_latencies)
    cold_p50 = statistics.median(cold_latencies)
    cold_p95 = max(cold_latencies)

    warm_mean = statistics.mean(warm_latencies)
    warm_p50 = statistics.median(warm_latencies)
    warm_p95 = max(warm_latencies)

    inc_mean = statistics.mean(incremental_latencies)

    print("\n" + "=" * 80)
    print("BENCHMARK SUMMARY:")
    print(
        f"Cold Index Queries:  Mean={cold_mean:7.2f} ms | P50={cold_p50:7.2f} ms | P95={cold_p95:7.2f} ms"
    )
    print(
        f"Warm Cached Queries: Mean={warm_mean:7.2f} ms | P50={warm_p50:7.2f} ms | P95={warm_p95:7.2f} ms"
    )
    print(f"Incremental Updates: Mean={inc_mean:7.2f} ms")
    print("=" * 80)

    report_path = os.path.join("evaluation", "reports", "cold_warm_benchmark.md")
    with open(report_path, "w", encoding="utf-8") as fp:
        fp.write(f"""# ARIA Cold vs Warm vs Incremental Benchmark (v5)

## 1. Latency Breakdown

| Operational State | Mean Latency | P50 (Median) | P95 (Max) | Description |
| :--- | :--- | :--- | :--- | :--- |
| **Cold Index Queries** | **{cold_mean:.2f} ms** | {cold_p50:.2f} ms | {cold_p95:.2f} ms | Initial snapshot encounter, builds in-memory TestImpactIndex |
| **Warm Cached Queries** | **{warm_mean:.2f} ms** | **{warm_p50:.2f} ms** | **{warm_p95:.2f} ms** | Subsequent developer queries against indexed snapshot (interactive SLA) |
| **Incremental Update** | **{inc_mean:.2f} ms** | {min(incremental_latencies):.2f} ms | {max(incremental_latencies):.2f} ms | Single test file modified; updates inverted index in-place without rebuilding |

## 2. Per-Task Measurements

| Task ID | Repo | Cold Latency (ms) | Warm Latency (ms) | Speedup Factor |
| :--- | :--- | :--- | :--- | :--- |
""")
        for i, t in enumerate(tasks):
            c_l = cold_latencies[i]
            w_l = warm_latencies[i]
            ratio = c_l / w_l if w_l > 0 else 1.0
            fp.write(
                f"| `{t['task_id']}` | `{t['repository']}` | {c_l:.2f} ms | **{w_l:.2f} ms** | **{ratio:.1f}x** |\n"
            )

    print(f"\nWrote cold/warm benchmark report to {report_path}")


if __name__ == "__main__":
    run_benchmark()
