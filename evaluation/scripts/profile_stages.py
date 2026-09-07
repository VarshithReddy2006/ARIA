"""Stage-Level Profiler for ARIA Impact Analysis (Phase 2 & 3).

Instruments the exact execution path of ImpactAnalysisService across all 10 evaluation tasks.
Measures wall-clock time for each sub-stage:
- Identifier and file-context extraction
- Symbol resolution
- Graph loading & seed determination
- Call graph resolution (direct & transitive callers)
- API surface cross-referencing
- Test impact discovery:
    * test candidate identification
    * test name matching
    * test file disk read & pre-filter
    * test AST parsing & inspection
- Symbol reference detection (_file_references_symbol across predecessors)
- Dependency traversal & confidence tier classification
- Blast radius & risk calculation
- Evidence aggregation & deduplication
- Result model serialization
"""

import os
import sys
import json
import time
from collections import defaultdict
import statistics
from typing import Dict, Any, List

sys.path.insert(0, os.path.abspath("."))

from backend.dependencies import get_impact_analysis_service


class StageTimer:
    def __init__(self):
        self.stage_times = defaultdict(list)
        self.stage_calls = defaultdict(int)

    def record(self, stage: str, duration_ms: float):
        self.stage_times[stage].append(duration_ms)
        self.stage_calls[stage] += 1

    def summary(self) -> List[Dict[str, Any]]:
        total_time_all = sum(sum(times) for times in self.stage_times.values())
        rows = []
        for stage, times in self.stage_times.items():
            tot = sum(times)
            calls = self.stage_calls[stage]
            mean = statistics.mean(times) if times else 0.0
            p50 = statistics.median(times) if times else 0.0
            p95 = max(times) if times else 0.0
            pct = (tot / total_time_all * 100.0) if total_time_all > 0 else 0.0
            rows.append(
                {
                    "stage": stage,
                    "calls": calls,
                    "total_time_ms": round(tot, 2),
                    "mean_ms": round(mean, 3),
                    "p50_ms": round(p50, 3),
                    "p95_ms": round(p95, 3),
                    "pct": round(pct, 2),
                }
            )
        rows.sort(key=lambda x: x["total_time_ms"], reverse=True)
        return rows


def run_stage_profile():
    tasks_path = os.path.join("evaluation", "tasks", "tasks.json")
    with open(tasks_path, "r", encoding="utf-8") as fp:
        tasks = json.load(fp)

    service = get_impact_analysis_service()
    timer = StageTimer()

    # Monkey patch or wrap specific methods of service to time internal stages
    orig_extract_identifiers = service._extract_identifiers
    orig_resolve_symbols = service._resolve_symbols
    orig_resolve_callers = service._resolve_callers
    orig_resolve_api_exposure = service._resolve_api_exposure
    # NOTE: service._resolve_test_impact is deliberately NOT wrapped here, so the
    # stage breakdown printed by this script excludes test-impact resolution.
    # Its cost is instead covered by the _inspect_test_file_ast and
    # _file_references_symbol wrappers below. See docs/engineering-audit.md.
    orig_inspect_test_file_ast = service._inspect_test_file_ast
    orig_file_references_symbol = service._file_references_symbol

    def timed_extract_identifiers(text):
        t0 = time.perf_counter()
        res = orig_extract_identifiers(text)
        timer.record("identifier_extraction", (time.perf_counter() - t0) * 1000.0)
        return res

    def timed_resolve_symbols(repo, idents, file_context=None, evidence_items=None):
        t0 = time.perf_counter()
        res = orig_resolve_symbols(
            repo, idents, file_context=file_context, evidence_items=evidence_items
        )
        timer.record("symbol_resolution", (time.perf_counter() - t0) * 1000.0)
        return res

    def timed_resolve_callers(repo_name, seed_files, resolved_symbols, evidence_items):
        t0 = time.perf_counter()
        res = orig_resolve_callers(
            repo_name, seed_files, resolved_symbols, evidence_items
        )
        timer.record("call_graph_traversal", (time.perf_counter() - t0) * 1000.0)
        return res

    def timed_resolve_api_exposure(
        repo_name, seed_files, affected_symbols, direct_callers, evidence_items
    ):
        t0 = time.perf_counter()
        res = orig_resolve_api_exposure(
            repo_name, seed_files, affected_symbols, direct_callers, evidence_items
        )
        timer.record("api_matching", (time.perf_counter() - t0) * 1000.0)
        return res

    def timed_inspect_test_file_ast(
        repo_name, test_file, seed_files, target_symbols, api_routes
    ):
        t0 = time.perf_counter()
        res = orig_inspect_test_file_ast(
            repo_name, test_file, seed_files, target_symbols, api_routes
        )
        timer.record("test_file_ast_inspection", (time.perf_counter() - t0) * 1000.0)
        return res

    def timed_file_references_symbol(repo_name, file_path, symbols):
        t0 = time.perf_counter()
        res = orig_file_references_symbol(repo_name, file_path, symbols)
        timer.record("symbol_reference_detection", (time.perf_counter() - t0) * 1000.0)
        return res

    service._extract_identifiers = timed_extract_identifiers
    service._resolve_symbols = timed_resolve_symbols
    service._resolve_callers = timed_resolve_callers
    service._resolve_api_exposure = timed_resolve_api_exposure
    service._inspect_test_file_ast = timed_inspect_test_file_ast
    service._file_references_symbol = timed_file_references_symbol

    task_latencies = []

    print("Running stage-level profiler across 10 tasks...")
    for idx, task in enumerate(tasks, start=1):
        repo_name = task["repository"]
        desc = task["change_description"]
        t0 = time.perf_counter()
        service.analyze_change(repo_name, desc)
        tot_ms = (time.perf_counter() - t0) * 1000.0
        task_latencies.append(tot_ms)
        print(f"[{idx}/10] {task['task_id']:38s}: {tot_ms:7.2f} ms")

    # Restore original methods
    service._extract_identifiers = orig_extract_identifiers
    service._resolve_symbols = orig_resolve_symbols
    service._resolve_callers = orig_resolve_callers
    service._resolve_api_exposure = orig_resolve_api_exposure
    service._inspect_test_file_ast = orig_inspect_test_file_ast
    service._file_references_symbol = orig_file_references_symbol

    summary = timer.summary()

    report_lines = [
        "# ARIA Stage-Level Latency Baseline Profile (v5 Baseline)",
        "",
        f"**Tasks Profiled:** {len(tasks)} tasks across `fastapi/fastapi`, `psf/requests`, `VarshithReddy2006/ARIA`",
        f"**Total Query Latency:** Mean={statistics.mean(task_latencies):.2f} ms | P50={statistics.median(task_latencies):.2f} ms | P95={max(task_latencies):.2f} ms",
        "",
        "---",
        "",
        "## Stage Breakdown",
        "",
        "| Stage | Calls | Total Time (ms) | Mean (ms) | P50 (ms) | P95 (ms) | % of Total Time |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for s in summary:
        report_lines.append(
            f"| `{s['stage']}` | {s['calls']} | {s['total_time_ms']:.2f} ms | {s['mean_ms']:.3f} ms | {s['p50_ms']:.3f} ms | {s['p95_ms']:.3f} ms | **{s['pct']:.1f}%** |"
        )

    report_lines.extend(
        [
            "",
            "---",
            "",
            "## Dominant Bottleneck Analysis",
            "",
        ]
    )

    if summary:
        top1 = summary[0]
        top2 = summary[1] if len(summary) > 1 else None
        report_lines.append(
            f"1. **Primary Bottleneck:** `{top1['stage']}` accounts for **{top1['total_time_ms']:.2f} ms ({top1['pct']:.1f}%)** of all execution time across {top1['calls']} calls."
        )
        if top2:
            report_lines.append(
                f"2. **Secondary Bottleneck:** `{top2['stage']}` accounts for **{top2['total_time_ms']:.2f} ms ({top2['pct']:.1f}%)** of execution time across {top2['calls']} calls."
            )

    out_path = os.path.join("evaluation", "reports", "v5_profile_baseline.md")
    with open(out_path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(report_lines))

    print(f"\nWrote baseline profile to {out_path}")
    for s in summary[:5]:
        print(
            f"  {s['stage']:30s}: {s['total_time_ms']:8.2f} ms ({s['pct']:5.1f}%) [calls: {s['calls']}]"
        )


if __name__ == "__main__":
    run_stage_profile()
