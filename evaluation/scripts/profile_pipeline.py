"""Pipeline Latency Profiler: Profiles the impact analysis pipeline across evaluation tasks."""

import os
import sys
import json
import time
import statistics

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath("."))

from backend.dependencies import get_impact_analysis_service


def profile():
    tasks_path = os.path.join("evaluation", "tasks", "tasks.json")
    with open(tasks_path, "r", encoding="utf-8") as fp:
        tasks = json.load(fp)

    service = get_impact_analysis_service()

    total_latencies = []
    task_profiles = []

    print(f"Profiling impact analysis pipeline across {len(tasks)} tasks...")
    print("=" * 80)

    for idx, task in enumerate(tasks, start=1):
        repo_name = task["repository"]
        desc = task["change_description"]
        task_id = task["task_id"]

        t0 = time.perf_counter()
        res = service.analyze_change(repo_name, desc)
        t_total = (time.perf_counter() - t0) * 1000.0

        total_latencies.append(t_total)
        task_profiles.append(
            {
                "task_id": task_id,
                "repo": repo_name,
                "total_ms": round(t_total, 2),
                "affected_files": len(
                    res.directly_affected_files + res.indirectly_affected_files
                ),
                "affected_tests": len(res.affected_tests),
            }
        )
        print(f"[{idx}/{len(tasks)}] {task_id:38s}: {t_total:7.2f} ms")

    p50 = statistics.median(total_latencies)
    p95 = (
        statistics.quantiles(total_latencies, n=20)[18]
        if len(total_latencies) >= 20
        else max(total_latencies)
    )
    mean = statistics.mean(total_latencies)

    print("\n" + "=" * 80)
    print("LATENCY SUMMARY:")
    print(
        f"Mean: {mean:.2f} ms | P50: {p50:.2f} ms | P95: {p95:.2f} ms | Min: {min(total_latencies):.2f} ms | Max: {max(total_latencies):.2f} ms"
    )

    # Generate profile report
    report_path = os.path.join("evaluation", "reports", "latency_profile_report.md")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as fp:
        fp.write(f"""# ARIA Impact Analysis Latency Profile Report

**Timestamp:** {time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())}  
**Tasks Profiled:** {len(tasks)} tasks across `fastapi/fastapi`, `psf/requests`, and `VarshithReddy2006/ARIA`.

---

## Latency Summary

| Metric | Measured Value |
| :--- | :--- |
| **Mean Latency** | **{mean:.2f} ms** |
| **P50 (Median)** | **{p50:.2f} ms** |
| **P95 Latency** | **{p95:.2f} ms** |
| **Minimum** | {min(total_latencies):.2f} ms |
| **Maximum** | {max(total_latencies):.2f} ms |

---

## Per-Task Breakdown

| Task ID | Repository | Latency (ms) | Affected Files | Affected Tests |
| :--- | :--- | :--- | :--- | :--- |
""")
        for tp in task_profiles:
            fp.write(
                f"| `{tp['task_id']}` | `{tp['repo']}` | {tp['total_ms']:.2f} ms | {tp['affected_files']} | {tp['affected_tests']} |\n"
            )

    print(f"\nWrote latency profile report to {report_path}")


if __name__ == "__main__":
    profile()
