"""Ingestion Service.

Encapsulates two helpers that were previously inlined in backend/api.py:

  - parse_repo_name()              — extract owner/repo from a GitHub URL
  - detect_tech_stack_and_deps()   — scan file list for languages + packages

Keeping these here makes them independently testable and removes the last
piece of business logic from the API layer.
"""

import json
import os
from typing import Any, Dict, List, Tuple


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

    Scans file extensions to determine languages and parses ``package.json``
    / ``requirements.txt`` manifests to extract dependency names.

    Args:
        files: List of ``{path, content}`` dicts as returned by
               ``GitHubService.extract_source_files()``.

    Returns:
        A ``(tech_stack, dependencies)`` tuple where both elements are lists
        of strings.
    """
    tech_stack: set = set()
    dependencies: set = set()

    file_paths = [f["path"] for f in files]
    for p in file_paths:
        ext = os.path.splitext(p)[1].lower()
        if ext == ".py":
            tech_stack.add("Python")
        elif ext in (".js", ".jsx"):
            tech_stack.add("JavaScript")
        elif ext in (".ts", ".tsx"):
            tech_stack.add("TypeScript")
        elif ext == ".html":
            tech_stack.add("HTML")
        elif ext == ".css":
            tech_stack.add("CSS")
        elif ext == ".go":
            tech_stack.add("Go")
        elif ext == ".rs":
            tech_stack.add("Rust")
        elif ext == ".java":
            tech_stack.add("Java")

        if p.endswith("package.json"):
            tech_stack.add("Node.js")
        elif p.endswith("requirements.txt") or p.endswith("pyproject.toml"):
            tech_stack.add("Python")

    for f in files:
        path = f.get("path", "")
        content = f.get("content", "")
        if not content:
            continue
        if path.endswith("package.json"):
            try:
                data = json.loads(content)
                for dep_key in ("dependencies", "devDependencies"):
                    if dep_key in data:
                        dependencies.update(data[dep_key].keys())
            except Exception:
                pass
        elif path.endswith("requirements.txt"):
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    pkg = (
                        line.split("=")[0]
                        .split(">")[0]
                        .split("<")[0]
                        .split("[")[0]
                        .strip()
                    )
                    if pkg:
                        dependencies.add(pkg)

    return list(tech_stack), list(dependencies)
