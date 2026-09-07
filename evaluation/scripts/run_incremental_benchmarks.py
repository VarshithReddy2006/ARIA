"""Incremental analysis benchmarks: Compares fresh full index vs incremental updates (1, 3, 10 files)."""

import os
import sys
import time
import json
import tracemalloc

sys.path.insert(0, os.path.abspath("."))

from services.architecture_service import ArchitectureService
from services.symbol_service import SymbolService


def get_memory_mb() -> float:
    """Returns peak memory usage in MB via tracemalloc."""
    _, peak = tracemalloc.get_traced_memory()
    return round(peak / (1024 * 1024), 2)


def main():
    repo_name = "psf/requests"
    repo_path = os.path.abspath("data/cloned_repos/psf_requests")

    if not os.path.exists(repo_path):
        print(f"Error: repo path not found: {repo_path}")
        return

    arch_svc = ArchitectureService()
    sym_svc = SymbolService()

    benchmarks = []
    scenarios = [
        ("fresh_full_index", set()),
        ("incremental_1_file", {"src/requests/sessions.py"}),
        (
            "incremental_3_files",
            {
                "src/requests/sessions.py",
                "src/requests/adapters.py",
                "src/requests/models.py",
            },
        ),
        (
            "incremental_10_files",
            {
                "src/requests/sessions.py",
                "src/requests/adapters.py",
                "src/requests/models.py",
                "src/requests/api.py",
                "src/requests/auth.py",
                "src/requests/certs.py",
                "src/requests/compat.py",
                "src/requests/cookies.py",
                "src/requests/exceptions.py",
                "src/requests/hooks.py",
            },
        ),
    ]

    print("Running Incremental Analysis Benchmarks on psf/requests...")
    print("=" * 70)

    for name, changed_files in scenarios:
        tracemalloc.start()
        start_time = time.perf_counter()

        if name == "fresh_full_index":
            res_arch = arch_svc.build(repo_name, repo_path=repo_path)
            sym_svc.build(repo_name, repo_path=repo_path)
            parsed_count = res_arch.get("files_parsed", 0)
        else:
            res_arch = arch_svc.build_partial(
                repo_name, changed_files, repo_path=repo_path
            )
            sym_svc.build_partial(repo_name, changed_files, repo_path=repo_path)
            parsed_count = len(changed_files)

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        peak_mb = get_memory_mb()
        tracemalloc.stop()

        benchmarks.append(
            {
                "scenario": name,
                "changed_file_count": len(changed_files),
                "reparsed_files": parsed_count,
                "latency_ms": round(elapsed_ms, 2),
                "peak_memory_mb": peak_mb,
            }
        )
        print(
            f"[{name}] Reparsed: {parsed_count} files | Latency: {elapsed_ms:.1f} ms | Memory: {peak_mb:.1f} MB"
        )

    out_path = os.path.join("evaluation", "results", "incremental_benchmarks.json")
    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(benchmarks, fp, indent=2)
    print(f"\nSaved benchmark results to {out_path}")


if __name__ == "__main__":
    main()
