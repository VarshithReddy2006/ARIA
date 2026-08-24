"""Ingestion Service.

Encapsulates helper functions for repository ingestion:
  - parse_repo_name()              — extract owner/repo from a GitHub URL
  - detect_tech_stack_and_deps()   — scan file list with deterministic weighted scoring
"""

import json
import os
import re
from collections import defaultdict
from typing import Any, Dict, List, Tuple

from core.file_classifier import classify_file


def parse_repo_name(url: str) -> str:
    """Parse owner/repo from a GitHub URL or bare owner/repo string.

    Args:
        url: A GitHub HTTPS URL or an ``owner/repo`` identifier.

    Returns:
        The ``owner/repo`` portion of the URL, e.g. ``"fastapi/fastapi"``.
    """
    url = url.strip()
    if url.endswith(".git"):
        url = url[:-4]
    parts = url.split("github.com/")
    if len(parts) > 1:
        return parts[1]
    return url


def detect_tech_stack_and_deps(
    files: List[Dict[str, Any]],
) -> Tuple[List[str], List[str]]:
    """Detect the language tech stack and package dependencies from a file list.

    Uses deterministic, weighted scoring prioritizing production source code
    over documentation assets, examples, and test fixtures.

    Args:
        files: List of ``{path, content}`` dicts as returned by
               ``GitHubService.extract_source_files()``.

    Returns:
        A ``(tech_stack, dependencies)`` tuple where ``tech_stack`` is sorted
        by dominance score descending (primary language first) and ``dependencies``
        is a sorted list of extracted package dependencies.
    """
    language_scores: Dict[str, float] = defaultdict(float)
    dependencies: set = set()

    for f in files:
        path = f.get("path", "")
        content = f.get("content", "")
        classification = classify_file(path)
        lang = classification.get("language")
        weight = classification.get("weight", 1.0)

        # Skip non-programming generic text categories from primary stack unless relevant
        if lang and lang not in (
            "Text",
            "JSON",
            "YAML",
            "XML",
            "TOML",
            "Markdown",
            "Documentation",
        ):
            # Size-boosted weight: production lines of code / content size give stronger signal
            content_lines = max(1, len(content.splitlines())) if content else 1
            line_factor = min(10.0, 1.0 + (content_lines / 100.0))
            language_scores[lang] += weight * line_factor

        # ── Manifest parsing ────────────────────────────────────────────────
        fn = os.path.basename(path).lower()
        if fn == "package.json" and content:
            language_scores["JavaScript"] += 15.0
            language_scores["Node.js"] += 10.0
            try:
                data = json.loads(content)
                for dep_key in ("dependencies", "devDependencies"):
                    if dep_key in data and isinstance(data[dep_key], dict):
                        dependencies.update(data[dep_key].keys())
            except Exception:
                pass
        elif fn == "pyproject.toml" and content:
            language_scores["Python"] += 25.0
            # Extract dependencies from pyproject.toml
            deps_matches = re.findall(
                r'["\']([a-zA-Z0-9_\-\[\]]+)(?:[><=~^!].*?)?["\']', content
            )
            for m in deps_matches:
                pkg = m.split("[")[0].strip()
                if pkg and len(pkg) > 1 and not pkg.startswith("."):
                    dependencies.add(pkg)
        elif fn.startswith("requirements") and content:
            language_scores["Python"] += 20.0
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("-"):
                    pkg = (
                        line.split("=")[0]
                        .split(">")[0]
                        .split("<")[0]
                        .split("~")[0]
                        .split("[")[0]
                        .strip()
                    )
                    if pkg:
                        dependencies.add(pkg)
        elif fn == "cargo.toml" and content:
            language_scores["Rust"] += 25.0
        elif fn == "go.mod" and content:
            language_scores["Go"] += 25.0

    # Sort tech stack deterministically by score descending
    sorted_stack = sorted(
        language_scores.keys(),
        key=lambda lang_name: (-language_scores[lang_name], lang_name),
    )

    # Filter out secondary web assets (e.g. CSS, HTML) if a strong backend/systems language dominates
    if len(sorted_stack) > 1:
        top_lang = sorted_stack[0]
        top_score = language_scores[top_lang]
        filtered_stack = []
        for lang_name in sorted_stack:
            score = language_scores[lang_name]
            # Keep if significant relative to top (at least 2% of top score)
            if score >= max(1.0, top_score * 0.02):
                filtered_stack.append(lang_name)
        sorted_stack = filtered_stack

    return sorted_stack, sorted(list(dependencies))
