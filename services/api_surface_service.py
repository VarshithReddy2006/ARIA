"""API Surface Intelligence Service.

Orchestrates the full API surface analysis pipeline:
  1. Load SymbolIndex (built by SymbolService — no re-parsing).
  2. Load parsed file metadata (TreeSitterService.parse_file output) to obtain
     JS/TS export lists — already built during /api/architecture/build, so no
     additional AST walk is performed.
  3. Delegate each symbol to SymbolClassifier for classification.
  4. Cross-reference with CallGraph fan-in to identify orphaned public APIs.
  5. Compute aggregate statistics.
  6. Persist to data/api_surface/{owner}_{repo}.json using the same atomic
     write + _schema_version pattern as ArchitectureService and SymbolService.

Design:
  - Zero LLM calls.
  - Zero duplicate AST parsing — reuses SymbolService.load() output.
  - SymbolClassifier is injected for testability.
  - BreakingChangeAnalyzer is a separate stateless utility (not injected).
  - Generator-based build() for SSE streaming, identical to GitHistoryService.
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional, Set

from models.api_surface import (
    APISurface,
    APISurfaceStats,
    ClassifiedSymbol,
    Visibility,
    ApiKind,
    ApiStatus,
)
from services.symbol_service import SymbolService
from services.tree_sitter_service import TreeSitterService
from services.symbol_classifier import SymbolClassifier
from services.architecture_service import ArchitectureService
from core.repository_context import RepositoryContext
from storage.snapshot_store import SnapshotStore
from core.cache import AnalysisCache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
_API_SURFACE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "api_surface",
)
_SCHEMA_VERSION = 1


class APISurfaceService:
    """Builds and queries the API surface index for a repository."""

    @property
    def schema_version(self) -> int:
        return _SCHEMA_VERSION

    @classmethod
    def get_schema_version(cls) -> int:
        return _SCHEMA_VERSION

    def __init__(
        self,
        symbol_service: Optional[SymbolService] = None,
        architecture_service: Optional[ArchitectureService] = None,
        api_surface_dir: str = _API_SURFACE_DIR,
        snapshot_store: Optional[SnapshotStore] = None,
        analysis_cache: Optional[AnalysisCache] = None,
    ) -> None:
        self.symbol_service = symbol_service or SymbolService()
        self.architecture_service = architecture_service or ArchitectureService()
        self.api_surface_dir = api_surface_dir
        self._ts = TreeSitterService()
        os.makedirs(self.api_surface_dir, exist_ok=True)

        if snapshot_store is None:
            if api_surface_dir != _API_SURFACE_DIR:
                parent_dir = os.path.dirname(api_surface_dir)
                dir_name = os.path.basename(api_surface_dir)
                from storage.snapshot_store import JsonSnapshotStore

                self.snapshot_store = JsonSnapshotStore(
                    base_dir=parent_dir, key_map={"api_surface": dir_name}
                )
            else:
                from storage.snapshot_store import JsonSnapshotStore

                self.snapshot_store = JsonSnapshotStore()
        else:
            self.snapshot_store = snapshot_store

        self.analysis_cache = analysis_cache or AnalysisCache()

    # ------------------------------------------------------------------
    # Public build API (generator for SSE streaming)
    # ------------------------------------------------------------------

    def build(
        self,
        repo_name: str,
        files: Optional[List[Dict[str, str]]] = None,
        context: Optional[RepositoryContext] = None,
    ) -> Generator[Dict[str, Any], None, APISurface]:
        """Build the API surface index.

        Provides backward compatibility by delegating to build_full.
        """
        return self.build_full(repo_name, context=context, files=files)

    def build_partial(
        self,
        repo_name: str,
        changed_files: Set[str],
        context: Optional[RepositoryContext] = None,
        files: Optional[List[Dict[str, str]]] = None,
    ) -> Generator[Dict[str, Any], None, APISurface]:
        """Incremental build for API Surface (delegates to build_full since it reuses parsed_files)."""
        return self.build_full(repo_name, context=context, files=files)

    def build_full(
        self,
        repo_name: str,
        context: Optional[RepositoryContext] = None,
        files: Optional[List[Dict[str, str]]] = None,
    ) -> Generator[Dict[str, Any], None, APISurface]:
        """Build API Surface by reusing parsed_files cache."""
        yield {"status": "loading_symbols", "message": "Loading symbol index…"}

        if context is not None:
            symbol_index = context.symbol_index
        else:
            symbol_index = self.symbol_service.load(repo_name)

        if symbol_index is None:
            raise ValueError(
                f"No symbol index found for '{repo_name}'. "
                "Run POST /api/architecture/build first."
            )

        yield {
            "status": "loading_arch",
            "message": "Loading architecture summary for entry points…",
        }

        if context is not None:
            arch_summary = self.architecture_service.get_summary(repo_name)
        else:
            arch_summary = self.architecture_service.get_summary(repo_name)

        entry_point_files: Set[str] = set(
            arch_summary.entry_points if arch_summary else []
        )

        if files is None:
            if context and context.repo_path:
                files = self.symbol_service._walk_repo(context.repo_path)
            else:
                files = []

        yield {
            "status": "building_file_index",
            "message": f"Indexing {len(files)} source files…",
        }

        # Build content map and parsed metadata map
        content_map: Dict[str, str] = {f["path"]: f.get("content", "") for f in files}

        # Load cached parsed files list to avoid redundant Tree-Sitter AST parsing
        parsed_map: Dict[str, Dict[str, Any]] = {}
        parsed_files_data = self.snapshot_store.load(repo_name, "parsed_files")
        if parsed_files_data and "parsed" in parsed_files_data:
            for p in parsed_files_data["parsed"]:
                path = p.get("file_path")
                if path:
                    parsed_map[path] = p
        else:
            # Fallback to direct parsing if parsed_files snapshot is missing
            for f in files:
                path = f.get("path", "")
                content = f.get("content", "")
                if not path or not content:
                    continue
                result = self._ts.parse_file(path, content)
                if result:
                    parsed_map[path] = result

        yield {
            "status": "classifying",
            "message": f"Classifying {symbol_index.symbol_count} symbols…",
        }

        # ── Try to load call graph fan-in for orphan detection ─────────
        fan_in_map: Dict[str, int] = self._load_fan_in(repo_name, context=context)

        # ── File-level caches to avoid re-computing per symbol ─────────
        all_list_cache: Dict[str, Optional[Set[str]]] = {}
        exports_cache: Dict[str, Optional[List[str]]] = {}

        classified: List[ClassifiedSymbol] = []

        for sym in symbol_index.symbols:
            fp = sym.file_path
            content = content_map.get(fp, "")

            # Python __all__ (compute once per file)
            if fp not in all_list_cache:
                if sym.language == "python":
                    all_list_cache[fp] = SymbolClassifier.extract_python_all(content)
                else:
                    all_list_cache[fp] = None

            # JS/TS exports list (from TreeSitter parse, computed once per file)
            if fp not in exports_cache:
                p = parsed_map.get(fp)
                exports_cache[fp] = p.get("exports") if p else None

            # Call graph fan-in for this symbol's node_id
            node_id = (
                f"{fp}::{sym.parent_class + '.' if sym.parent_class else ''}{sym.name}"
            )
            fan_in = fan_in_map.get(node_id, 0)

            cs = SymbolClassifier.classify(
                symbol=sym,
                file_content=content,
                parsed_exports=exports_cache[fp],
                all_list=all_list_cache[fp],
                entry_point_files=entry_point_files,
                call_graph_fan_in=fan_in,
            )
            classified.append(cs)

        yield {
            "status": "computing_stats",
            "message": "Computing aggregate statistics…",
        }

        stats = self._compute_stats(classified)

        yield {"status": "persisting", "message": "Saving API surface index…"}

        surface = APISurface(
            repo=repo_name,
            generated_at=datetime.now(timezone.utc).isoformat(),
            symbols=classified,
            stats=stats,
        )
        self._save(repo_name, surface)

        yield {
            "status": "complete",
            "message": (
                f"✓ API surface built: {stats.public_count} public, "
                f"{stats.internal_count} internal, "
                f"{stats.deprecated_count} deprecated, "
                f"{stats.route_count} routes"
            ),
        }

        return surface

    # ------------------------------------------------------------------
    # Public query API
    # ------------------------------------------------------------------

    def load(self, repo_name: str) -> Optional[APISurface]:
        """Load a persisted API surface report."""
        cached = self.analysis_cache.get(repo_name, "api_surface", _SCHEMA_VERSION)
        if cached is not None:
            return cached

        data = self.snapshot_store.load(repo_name, "api_surface")
        if data is None:
            return None

        stored_ver = data.get("_schema_version", 0)
        if stored_ver < _SCHEMA_VERSION:
            logger.warning(
                "Discarding stale API surface report for %s (v%d < v%d)",
                repo_name,
                stored_ver,
                _SCHEMA_VERSION,
            )
            return None

        try:
            filtered = {k: v for k, v in data.items() if not k.startswith("_")}
            surface = APISurface(**filtered)
            self.analysis_cache.set(repo_name, "api_surface", surface, _SCHEMA_VERSION)
            return surface
        except Exception as exc:
            logger.error("Failed to deserialise API surface for %s: %s", repo_name, exc)
            return None

    def surface_exists(self, repo_name: str) -> bool:
        return self.snapshot_store.exists(repo_name, "api_surface")

    def get_public(self, repo_name: str) -> List[ClassifiedSymbol]:
        surface = self.load(repo_name)
        if surface is None:
            return []
        return [s for s in surface.symbols if s.visibility == Visibility.PUBLIC]

    def get_internal(self, repo_name: str) -> List[ClassifiedSymbol]:
        surface = self.load(repo_name)
        if surface is None:
            return []
        return [s for s in surface.symbols if s.visibility == Visibility.INTERNAL]

    def get_deprecated(self, repo_name: str) -> List[ClassifiedSymbol]:
        surface = self.load(repo_name)
        if surface is None:
            return []
        return [s for s in surface.symbols if s.status == ApiStatus.DEPRECATED]

    def get_routes(self, repo_name: str) -> List[ClassifiedSymbol]:
        surface = self.load(repo_name)
        if surface is None:
            return []
        return [s for s in surface.symbols if s.api_kind == ApiKind.ROUTE]

    def get_orphans(self, repo_name: str) -> List[ClassifiedSymbol]:
        """Return public symbols with no callers (potentially unused public API)."""
        surface = self.load(repo_name)
        if surface is None:
            return []
        return [s for s in surface.symbols if s.is_orphan]

    def get_symbol(
        self, repo_name: str, symbol_name: str
    ) -> Optional[ClassifiedSymbol]:
        """Return the first symbol matching symbol_name (exact name match)."""
        surface = self.load(repo_name)
        if surface is None:
            return None
        for s in surface.symbols:
            if s.name == symbol_name or s.qualified == symbol_name:
                return s
        return None

    def search(
        self,
        repo_name: str,
        query: str,
        visibility: Optional[str] = None,
        kind: Optional[str] = None,
        limit: int = 50,
    ) -> List[ClassifiedSymbol]:
        """Search symbols by name substring with optional filters."""
        surface = self.load(repo_name)
        if surface is None:
            return []

        q = query.lower()
        results = []
        for s in surface.symbols:
            if q not in s.name.lower() and q not in s.qualified.lower():
                continue
            if visibility and s.visibility.value != visibility:
                continue
            if kind and s.api_kind.value != kind:
                continue
            results.append(s)
        return results[:limit]

    def get_stats(self, repo_name: str) -> Optional[APISurfaceStats]:
        surface = self.load(repo_name)
        if surface is None:
            return None
        return surface.stats

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_stats(symbols: List[ClassifiedSymbol]) -> APISurfaceStats:
        by_lang: Dict[str, int] = defaultdict(int)
        stats = APISurfaceStats()

        for s in symbols:
            stats.total_symbols += 1
            by_lang[s.language] += 1

            if s.visibility == Visibility.PUBLIC:
                stats.public_count += 1
            elif s.visibility == Visibility.INTERNAL:
                stats.internal_count += 1
            elif s.visibility == Visibility.PRIVATE:
                stats.private_count += 1
            else:
                stats.unknown_count += 1

            if s.status == ApiStatus.DEPRECATED:
                stats.deprecated_count += 1
            elif s.status == ApiStatus.EXPERIMENTAL:
                stats.experimental_count += 1

            if s.api_kind == ApiKind.ROUTE:
                stats.route_count += 1
            if s.api_kind in (ApiKind.MAIN_ENTRY, ApiKind.CLI_ENTRY):
                stats.entry_point_count += 1

            if s.is_orphan:
                stats.orphan_public_count += 1

        stats.by_language = dict(by_lang)
        return stats

    # ------------------------------------------------------------------
    # Call graph fan-in helper
    # ------------------------------------------------------------------

    def _load_fan_in(
        self, repo_name: str, context: Optional[RepositoryContext] = None
    ) -> Dict[str, int]:
        """Load fan-in counts from the call graph if available."""
        try:
            G = None
            if context is not None:
                G = context.call_graph
            if G is None:
                cached = self.analysis_cache.get(repo_name, "graphs", 1, subkey="call")
                if cached is not None:
                    G = cached
            if G is None and getattr(self, "graph_service", None) is not None:
                G = self.graph_service.load_graph(f"{repo_name}_call_graph")

            if G is None:
                return {}

            return {node: G.in_degree(node) for node in G.nodes()}
        except Exception as exc:
            logger.debug("Could not load call graph fan-in: %s", exc)
            return {}

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _surface_path(self, repo_name: str) -> str:
        return self.snapshot_store._get_path(repo_name, "api_surface")

    def _save(self, repo_name: str, surface: APISurface) -> None:
        payload = surface.model_dump()
        payload["_schema_version"] = _SCHEMA_VERSION
        payload["_built_at"] = int(time.time())
        self.snapshot_store.save(repo_name, "api_surface", payload)

    def _load_raw(self, repo_name: str) -> Optional[Dict[str, Any]]:
        return self.snapshot_store.load(repo_name, "api_surface")
