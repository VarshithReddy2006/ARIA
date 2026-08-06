"""Repository context abstraction representing immutable lazy repository state (PH2-002)."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import networkx as nx

from models.api_surface import APISurface
from models.churn import ChurnSummary
from models.symbol import SymbolIndex
from core.cache import AnalysisCache
from storage.snapshot_store import SnapshotStore

logger = logging.getLogger(__name__)


class RepositoryContext:
    """Immutable, lazy-loaded repository state serving as single source of truth."""

    def __init__(
        self,
        repo_name: str,
        repo_path: Optional[str] = None,
        cache: Optional[AnalysisCache] = None,
        store: Optional[SnapshotStore] = None,
        graph_service: Optional[Any] = None,
    ) -> None:
        """Initialise the repository context.

        Args:
            repo_name: Owner/repo identifier.
            repo_path: Local filesystem path where repo is cloned.
            cache: analysis cache instance.
            store: snapshot store instance.
            graph_service: graph service instance.
        """
        self._repo_name = repo_name
        self._repo_path = repo_path

        if cache is not None:
            self._cache = cache
        else:
            from core.cache import AnalysisCache
            self._cache = AnalysisCache()

        if store is not None:
            self._store = store
        else:
            from storage.snapshot_store import JsonSnapshotStore

            self._store = JsonSnapshotStore()

        if graph_service is not None:
            self._graph_service = graph_service
        else:
            from services.graph_service import GraphService

            self._graph_service = GraphService()

    @property
    def repo_name(self) -> str:
        """Return the owner/repo name."""
        return self._repo_name

    @property
    def repo_path(self) -> Optional[str]:
        """Return the absolute path to the repository on disk."""
        return self._repo_path

    @property
    def metadata(self) -> Dict[str, Any]:
        """Lazy load repository and build manifest metadata."""
        key = "metadata"
        cached = self._cache.get(self._repo_name, key, 1)
        if cached is not None:
            return cached

        # Check if manifest exists in store
        manifest_data = self._store.load(self._repo_name, "build_manifest")
        metadata = {
            "repo_name": self._repo_name,
            "repo_path": self._repo_path,
        }
        if manifest_data:
            metadata.update(manifest_data)

        self._cache.set(self._repo_name, key, metadata, 1)
        return metadata

    @property
    def symbol_index(self) -> Optional[SymbolIndex]:
        """Lazy load SymbolIndex model."""
        key = "symbols"
        schema_version = 1
        cached = self._cache.get(self._repo_name, key, schema_version)
        if cached is not None:
            return cached

        data = self._store.load(self._repo_name, key)
        if data is None:
            return None

        try:
            filtered = {k: v for k, v in data.items() if not k.startswith("_")}
            index = SymbolIndex.model_validate(filtered)
            self._cache.set(self._repo_name, key, index, schema_version)
            return index
        except Exception as exc:
            logger.error(
                "Failed to validate SymbolIndex for %s: %s",
                self._repo_name,
                exc,
            )
            return None

    @property
    def dependency_graph(self) -> Optional[nx.DiGraph]:
        """Lazy load dependency graph."""
        key = "graphs"
        subkey = "dependency"
        schema_version = 1
        cached = self._cache.get(self._repo_name, key, schema_version, subkey=subkey)
        if cached is not None:
            return cached

        graph = self._graph_service.load_graph(self._repo_name)
        if graph is not None:
            self._cache.set(self._repo_name, key, graph, schema_version, subkey=subkey)
        return graph

    @property
    def call_graph(self) -> Optional[nx.DiGraph]:
        """Lazy load call graph."""
        key = "graphs"
        subkey = "call"
        schema_version = 1
        cached = self._cache.get(self._repo_name, key, schema_version, subkey=subkey)
        if cached is not None:
            return cached

        graph = self._graph_service.load_graph(f"{self._repo_name}_call_graph")
        if graph is not None:
            self._cache.set(self._repo_name, key, graph, schema_version, subkey=subkey)
        return graph

    def get_git_history(self, since_days: int = 30) -> Optional[ChurnSummary]:
        """Lazy load git churn history for specified timeframe."""
        key = "churn"
        subkey = f"{since_days}d"
        schema_version = 1
        cached = self._cache.get(self._repo_name, key, schema_version, subkey=subkey)
        if cached is not None:
            return cached

        data = self._store.load(self._repo_name, key, subkey=subkey)
        if data is None:
            return None

        try:
            filtered = {k: v for k, v in data.items() if not k.startswith("_")}
            summary = ChurnSummary.model_validate(filtered)
            self._cache.set(
                self._repo_name, key, summary, schema_version, subkey=subkey
            )
            return summary
        except Exception as exc:
            logger.error(
                "Failed to validate ChurnSummary for %s (%s): %s",
                self._repo_name,
                subkey,
                exc,
            )
            return None

    @property
    def git_history(self) -> Optional[ChurnSummary]:
        """Lazy load default (30-day) git churn history summary."""
        return self.get_git_history(30)

    @property
    def api_surface(self) -> Optional[APISurface]:
        """Lazy load APISurface model."""
        key = "api_surface"
        schema_version = 1
        cached = self._cache.get(self._repo_name, key, schema_version)
        if cached is not None:
            return cached

        data = self._store.load(self._repo_name, key)
        if data is None:
            return None

        try:
            filtered = {k: v for k, v in data.items() if not k.startswith("_")}
            surface = APISurface.model_validate(filtered)
            self._cache.set(self._repo_name, key, surface, schema_version)
            return surface
        except Exception as exc:
            logger.error(
                "Failed to validate APISurface for %s: %s",
                self._repo_name,
                exc,
            )
            return None

    @property
    def module_stability(self) -> Optional[Dict[str, Any]]:
        """Lazy load stability analysis dictionary."""
        key = "stability"
        schema_version = 1
        cached = self._cache.get(self._repo_name, key, schema_version)
        if cached is not None:
            return cached

        data = self._store.load(self._repo_name, key)
        if data is None:
            return None

        filtered = {k: v for k, v in data.items() if not k.startswith("_")}
        self._cache.set(self._repo_name, key, filtered, schema_version)
        return filtered

    @property
    def dependency_smells(self) -> Optional[Dict[str, Any]]:
        """Lazy load dependency smells dictionary."""
        key = "dependency_smells"
        schema_version = 1
        cached = self._cache.get(self._repo_name, key, schema_version)
        if cached is not None:
            return cached

        data = self._store.load(self._repo_name, key)
        if data is None:
            return None

        filtered = {k: v for k, v in data.items() if not k.startswith("_")}
        self._cache.set(self._repo_name, key, filtered, schema_version)
        return filtered

    @property
    def architecture_health(self) -> Optional[Dict[str, Any]]:
        """Lazy load architecture health dictionary."""
        key = "health"
        schema_version = 1
        cached = self._cache.get(self._repo_name, key, schema_version)
        if cached is not None:
            return cached

        data = self._store.load(self._repo_name, key)
        if data is None:
            return None

        filtered = {k: v for k, v in data.items() if not k.startswith("_")}
        self._cache.set(self._repo_name, key, filtered, schema_version)
        return filtered
