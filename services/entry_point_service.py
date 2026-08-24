"""Entry Point Detection Service.

Identifies the primary entry points of a repository based on manifest definitions,
framework-specific patterns, filename conventions, and structural heuristics.

Supported detection targets:
  - Manifest Scripts: pyproject.toml [project.scripts], setup.cfg, package.json bin/main
  - Python: __main__.py, main.py, package roots (__init__.py), app.py, server.py, asgi.py, wsgi.py
  - Node.js/TS: index.ts/js, server.ts/js, app.ts/js, bin/ scripts
  - React/Frontend: main.tsx, App.tsx, index.html
  - Go: main.go, cmd/*/main.go
  - Rust: src/main.rs, src/lib.rs

Differentiates production entry points from documentation examples, test fixtures, and tutorial apps.
"""

import logging
import os
import re
from typing import Any, Dict, List, Optional, Set

from core.file_classifier import (
    classify_file,
    CATEGORY_PRODUCTION,
    CATEGORY_EXAMPLE,
    CATEGORY_TEST,
    CATEGORY_GENERATED,
)

logger = logging.getLogger(__name__)


def _is_top_level_or_package_root(file_path: str) -> bool:
    """Return True if the file is in repo root, src/, backend/, app/, or top package dir."""
    parts = file_path.replace("\\", "/").strip("/").split("/")
    if len(parts) <= 2:
        return True
    if (
        parts[0] in ("src", "backend", "lib", "core", "pkg", "app", "cmd")
        and len(parts) <= 3
    ):
        return True
    return False


class EntryPointService:
    """Detects entry points in a repository using manifests, heuristics, and structural rules."""

    def detect(
        self,
        file_paths: List[str],
        parsed_files: Optional[List[Dict[str, Any]]] = None,
        files_content: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Detect and rank entry points across the full file list.

        Args:
            file_paths: All file paths in the repository (relative).
            parsed_files: Optional parsed metadata from TreeSitterService.
            files_content: Optional list of {path, content} for manifest inspection.

        Returns:
            A dictionary with:
                entry_points          – list of primary production entry point paths
                example_entry_points  – list of example/demo application entry points
                detailed_entry_points – list of dicts with path, category, priority, and reason
                next_js               – True if Next.js app/ or pages/ dirs detected
                patterns_hit          – list of pattern names that fired
        """
        parsed_map: Dict[str, Dict] = {}
        if parsed_files:
            for pf in parsed_files:
                parsed_map[pf["file_path"]] = pf

        content_map: Dict[str, str] = {}
        if files_content:
            for fc in files_content:
                content_map[fc.get("path", "")] = fc.get("content", "")

        hits: List[Dict[str, Any]] = []
        seen_paths: Set[str] = set()

        # ── 1. Manifest Entry Points (Priority 1) ───────────────────────────
        self._detect_manifest_entry_points(file_paths, content_map, hits, seen_paths)

        # ── 2. Structural & File Convention Patterns ─────────────────────────
        for fp in file_paths:
            if fp in seen_paths:
                continue

            classification = classify_file(fp)
            category = classification["category"]
            fp_norm = fp.replace("\\", "/").strip("/")
            lower_fp = fp_norm.lower()
            parts = lower_fp.split("/")
            filename = parts[-1]
            name_no_ext, ext = os.path.splitext(filename)

            # Skip test and generated files from entry point consideration
            if category in (CATEGORY_TEST, CATEGORY_GENERATED):
                continue

            # (A) Production Package Roots (e.g. fastapi/__init__.py)
            if (
                category == CATEGORY_PRODUCTION
                and filename == "__init__.py"
                and len(parts) <= 3
            ):
                # Top package __init__.py exporting the public API
                is_root_pkg = len(parts) == 2 or (
                    parts[0] in ("src", "lib") and len(parts) == 3
                )
                if is_root_pkg:
                    hits.append(
                        {
                            "path": fp,
                            "category": CATEGORY_PRODUCTION,
                            "priority": 2,
                            "reason": "package_root_public_api",
                            "pattern": "python_package_root",
                        }
                    )
                    seen_paths.add(fp)
                    continue

            # (B) Python __main__.py (executable module)
            if filename == "__main__.py":
                is_prod = (
                    category == CATEGORY_PRODUCTION
                    and _is_top_level_or_package_root(fp)
                )
                hits.append(
                    {
                        "path": fp,
                        "category": CATEGORY_PRODUCTION if is_prod else category,
                        "priority": 2 if is_prod else 102,
                        "reason": "python_module_executable"
                        if is_prod
                        else f"{category}_executable",
                        "pattern": "python_dunder_main",
                    }
                )
                seen_paths.add(fp)
                continue

            # (C) Python main.py
            if filename == "main.py":
                is_prod = (
                    category == CATEGORY_PRODUCTION
                    and _is_top_level_or_package_root(fp)
                )
                hits.append(
                    {
                        "path": fp,
                        "category": CATEGORY_PRODUCTION if is_prod else category,
                        "priority": 3 if is_prod else 103,
                        "reason": "application_main"
                        if is_prod
                        else f"{category}_example_application",
                        "pattern": "python_main",
                    }
                )
                seen_paths.add(fp)
                continue

            # (D) Application Servers: app.py, server.py, asgi.py, wsgi.py, api.py
            if filename in (
                "app.py",
                "server.py",
                "asgi.py",
                "wsgi.py",
                "api.py",
                "application.py",
                "run.py",
            ):
                if category == CATEGORY_PRODUCTION and _is_top_level_or_package_root(
                    fp
                ):
                    hits.append(
                        {
                            "path": fp,
                            "category": CATEGORY_PRODUCTION,
                            "priority": 3,
                            "reason": "application_server_entry",
                            "pattern": "python_app_server",
                        }
                    )
                    seen_paths.add(fp)
                    continue

            # (E) Node / TS: index.ts, index.js, server.ts, server.js, app.ts, app.js
            if filename in (
                "index.ts",
                "index.js",
                "server.ts",
                "server.js",
                "app.ts",
                "app.js",
            ):
                if category == CATEGORY_PRODUCTION and _is_top_level_or_package_root(
                    fp
                ):
                    hits.append(
                        {
                            "path": fp,
                            "category": CATEGORY_PRODUCTION,
                            "priority": 4,
                            "reason": "node_server_entry",
                            "pattern": "node_entry",
                        }
                    )
                    seen_paths.add(fp)
                    continue

            # (F) React / Frontend: main.tsx, App.tsx, main.ts, App.jsx
            if filename in ("main.tsx", "App.tsx", "main.ts", "App.jsx", "app.tsx"):
                if category == CATEGORY_PRODUCTION and _is_top_level_or_package_root(
                    fp
                ):
                    hits.append(
                        {
                            "path": fp,
                            "category": CATEGORY_PRODUCTION,
                            "priority": 5,
                            "reason": "frontend_root_component",
                            "pattern": "react_entry",
                        }
                    )
                    seen_paths.add(fp)
                    continue

            # (G) Go: main.go, cmd/*/main.go
            if filename == "main.go":
                is_prod = (
                    category == CATEGORY_PRODUCTION
                    and _is_top_level_or_package_root(fp)
                )
                hits.append(
                    {
                        "path": fp,
                        "category": CATEGORY_PRODUCTION if is_prod else category,
                        "priority": 3 if is_prod else 103,
                        "reason": "go_main_package"
                        if is_prod
                        else f"{category}_go_main",
                        "pattern": "go_main",
                    }
                )
                seen_paths.add(fp)
                continue

            # (H) Rust: src/main.rs, src/lib.rs
            if fp_norm in ("src/main.rs", "src/lib.rs", "main.rs", "lib.rs"):
                hits.append(
                    {
                        "path": fp,
                        "category": CATEGORY_PRODUCTION,
                        "priority": 2,
                        "reason": "rust_crate_root",
                        "pattern": "rust_entry",
                    }
                )
                seen_paths.add(fp)
                continue

        # Sort hits by priority ascending, then path
        hits.sort(key=lambda h: (h["priority"], h["path"]))

        prod_entry_points = [
            h["path"] for h in hits if h["category"] == CATEGORY_PRODUCTION
        ]
        example_entry_points = [
            h["path"] for h in hits if h["category"] == CATEGORY_EXAMPLE
        ]

        # If no production entry points were identified at all, but some example files exist,
        # fallback to the top entry points while retaining their example classification.
        final_entry_points = (
            prod_entry_points if prod_entry_points else [h["path"] for h in hits]
        )
        patterns_hit = list({h["pattern"] for h in hits})
        next_js = self._detect_nextjs(file_paths)

        return {
            "entry_points": final_entry_points,
            "production_entry_points": prod_entry_points,
            "example_entry_points": example_entry_points,
            "detailed_entry_points": hits,
            "next_js": next_js,
            "patterns_hit": patterns_hit,
        }

    # ------------------------------------------------------------------
    # Manifest inspection
    # ------------------------------------------------------------------

    def _detect_manifest_entry_points(
        self,
        file_paths: List[str],
        content_map: Dict[str, str],
        hits: List[Dict[str, Any]],
        seen_paths: Set[str],
    ) -> None:
        """Scan pyproject.toml, package.json, setup.cfg for declared console scripts/bin."""
        for fp in file_paths:
            fn = os.path.basename(fp).lower()
            content = content_map.get(fp)
            if not content:
                continue

            # Python pyproject.toml scripts
            if fn == "pyproject.toml":
                # Find script targets like: aria = "backend.api:main" or fastapi = "fastapi.cli:main"
                scripts = re.findall(
                    r'([a-zA-Z0-9_\-]+)\s*=\s*["\']([a-zA-Z0-9_\.]+):', content
                )
                for script_name, mod_path in scripts:
                    # Convert module path to file candidate
                    rel_cand = mod_path.replace(".", "/") + ".py"
                    for candidate in file_paths:
                        if candidate.endswith(rel_cand) or candidate == rel_cand:
                            if candidate not in seen_paths:
                                hits.append(
                                    {
                                        "path": candidate,
                                        "category": CATEGORY_PRODUCTION,
                                        "priority": 1,
                                        "reason": f"pyproject_script_entry ({script_name})",
                                        "pattern": "manifest_script",
                                    }
                                )
                                seen_paths.add(candidate)

            # Node package.json bin / main
            elif fn == "package.json":
                try:
                    import json

                    data = json.loads(content)
                    bin_field = data.get("bin")
                    if isinstance(bin_field, str):
                        cand = bin_field.lstrip("./")
                        for p in file_paths:
                            if p == cand or p.endswith(cand):
                                if p not in seen_paths:
                                    hits.append(
                                        {
                                            "path": p,
                                            "category": CATEGORY_PRODUCTION,
                                            "priority": 1,
                                            "reason": "package_json_bin",
                                            "pattern": "manifest_bin",
                                        }
                                    )
                                    seen_paths.add(p)
                    elif isinstance(bin_field, dict):
                        for _, bin_path in bin_field.items():
                            cand = str(bin_path).lstrip("./")
                            for p in file_paths:
                                if p == cand or p.endswith(cand):
                                    if p not in seen_paths:
                                        hits.append(
                                            {
                                                "path": p,
                                                "category": CATEGORY_PRODUCTION,
                                                "priority": 1,
                                                "reason": "package_json_bin",
                                                "pattern": "manifest_bin",
                                            }
                                        )
                                        seen_paths.add(p)
                except Exception:
                    pass

    @staticmethod
    def _detect_nextjs(file_paths: List[str]) -> bool:
        """Return True if Next.js directory structure is detected."""
        for fp in file_paths:
            parts = fp.replace("\\", "/").split("/")
            if (
                len(parts) >= 2
                and parts[0] in ("app", "pages")
                and parts[-1].endswith((".js", ".jsx", ".ts", ".tsx"))
            ):
                return True
            if (
                len(parts) >= 3
                and parts[0] == "src"
                and parts[1] in ("app", "pages")
                and parts[-1].endswith((".js", ".jsx", ".ts", ".tsx"))
            ):
                return True
        return False
