"""Application Service orchestrating repository searches."""

from typing import Optional

from ria.domain.search.entities import SearchResponse
from ria.domain.search.value_objects import SearchOptions, SearchQuery, SearchQueryType
from ria.ports.common.clock import ClockPort
from ria.ports.common.logger import LoggerPort
from ria.ports.common.metrics import MetricsPort
from ria.ports.search.engine import SearchEnginePort
from ria.ports.storage.fact_store import FactStorePort
from ria.ports.sync.registry import RepositoryRegistryPort


class SearchApplicationService:
    """Application Service coordinating repository state lookup and SearchEngine execution."""

    def __init__(
        self,
        search_engine: SearchEnginePort,
        fact_store: FactStorePort,
        registry: RepositoryRegistryPort,
        clock: ClockPort,
        logger: LoggerPort,
        metrics: MetricsPort,
    ) -> None:
        self._engine = search_engine
        self._fact_store = fact_store
        self._registry = registry
        self._clock = clock
        self._logger = logger
        self._metrics = metrics

    def search_symbol(self, repo_id_str: str, query_text: str, query_type_str: str = "EXACT", max_results: int = 50) -> SearchResponse:
        st = next((s for s in self._registry.list_all() if s.identity.repo_id.value == repo_id_str), None)
        if st is None or st.current_commit is None:
            raise ValueError(f"Repository '{repo_id_str}' is not registered or synchronized.")

        try:
            qtype = SearchQueryType[query_type_str.upper()]
        except KeyError:
            qtype = SearchQueryType.EXACT

        query = SearchQuery(query_text=query_text, query_type=qtype, options=SearchOptions(max_results=max_results))
        return self._engine.search(query, self._fact_store, st.identity, st.current_commit)

    def search_file(self, repo_id_str: str, query_text: str, max_results: int = 50) -> SearchResponse:
        st = next((s for s in self._registry.list_all() if s.identity.repo_id.value == repo_id_str), None)
        if st is None or st.current_commit is None:
            raise ValueError(f"Repository '{repo_id_str}' is not registered or synchronized.")

        query = SearchQuery(query_text=query_text, query_type=SearchQueryType.FILE, options=SearchOptions(max_results=max_results))
        return self._engine.search(query, self._fact_store, st.identity, st.current_commit)

    def search_module(self, repo_id_str: str, query_text: str, max_results: int = 50) -> SearchResponse:
        st = next((s for s in self._registry.list_all() if s.identity.repo_id.value == repo_id_str), None)
        if st is None or st.current_commit is None:
            raise ValueError(f"Repository '{repo_id_str}' is not registered or synchronized.")

        query = SearchQuery(query_text=query_text, query_type=SearchQueryType.MODULE, options=SearchOptions(max_results=max_results))
        return self._engine.search(query, self._fact_store, st.identity, st.current_commit)

    def autocomplete(self, repo_id_str: str, prefix: str, max_suggestions: int = 10) -> SearchResponse:
        st = next((s for s in self._registry.list_all() if s.identity.repo_id.value == repo_id_str), None)
        if st is None or st.current_commit is None:
            raise ValueError(f"Repository '{repo_id_str}' is not registered or synchronized.")

        query = SearchQuery(query_text=prefix, query_type=SearchQueryType.AUTOCOMPLETE, options=SearchOptions(max_results=max_suggestions))
        return self._engine.search(query, self._fact_store, st.identity, st.current_commit)
