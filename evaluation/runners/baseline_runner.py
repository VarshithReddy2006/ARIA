"""Baseline runner: Simulates conventional keyword/grep & naive text-chunk RAG."""

import os
import re
import time
from typing import Dict, Any, Set


class BaselineRunner:
    """Conventional code search & naive RAG baseline."""

    def __init__(self, repos_dir: str = "data/cloned_repos"):
        self.repos_dir = repos_dir

    def _resolve_repo_path(self, repo_name: str) -> str:
        safe_name = repo_name.replace("/", "_")
        path = os.path.join(self.repos_dir, safe_name)
        if not os.path.exists(path):
            path = os.path.join(
                self.repos_dir, safe_name.replace("VarshithReddy2006_", "")
            )
        return os.path.abspath(path)

    def run_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.perf_counter()

        repo_name = task["repository"]
        query = task["change_description"]
        repo_path = self._resolve_repo_path(repo_name)

        # 1. Extract search tokens (keywords and symbol names)
        tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{3,}", query)
        stop_words = {
            "modify",
            "change",
            "refactor",
            "update",
            "support",
            "method",
            "class",
            "file",
            "favor",
            "standard",
            "custom",
        }
        keywords = [t for t in tokens if t.lower() not in stop_words]

        found_files: Set[str] = set()
        found_callers: Set[str] = set()
        found_tests: Set[str] = set()

        if os.path.exists(repo_path):
            for root, _, files in os.walk(repo_path):
                # Skip .git and caches
                if ".git" in root or "__pycache__" in root or ".venv" in root:
                    continue
                for f in files:
                    if not (
                        f.endswith(".py") or f.endswith(".ts") or f.endswith(".tsx")
                    ):
                        continue
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, repo_path).replace("\\", "/")

                    try:
                        with open(
                            full_path, "r", encoding="utf-8", errors="ignore"
                        ) as fp:
                            content = fp.read()
                    except Exception:
                        continue

                    # Keyword match scoring
                    match_count = sum(1 for kw in keywords if kw in content)
                    if match_count > 0:
                        found_files.add(rel_path)
                        if "test" in rel_path.lower():
                            found_tests.add(rel_path)

                        # Naive caller extraction: lines with `def foo(` or calls
                        for kw in keywords:
                            if f"{kw}(" in content or f".{kw}(" in content:
                                # Heuristically extract function names in the file
                                defs = re.findall(
                                    r"def\s+([a-zA-Z0-9_]+)\s*\(", content
                                )
                                for d in defs[:2]:
                                    found_callers.add(d)
        else:
            # Fallback if repo clone isn't local
            found_files.update([kw for kw in keywords])

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        return {
            "task_id": task["task_id"],
            "approach": "baseline_search_rag",
            "latency_ms": round(latency_ms, 2),
            "predicted_files": sorted(list(found_files)),
            "predicted_callers": sorted(list(found_callers)),
            "predicted_tests": sorted(list(found_tests)),
            "predicted_api_surfaces": [],  # Naive RAG has no API surface model
            "predicted_risk": "medium",  # Naive RAG guessing medium
        }
