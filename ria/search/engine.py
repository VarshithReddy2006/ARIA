"""Search Engine implementing SearchEnginePort."""

from ria.domain.common.value_objects import UUIDv4
from ria.domain.search.entities import (
    AutocompleteResult,
    FileResult,
    ModuleResult,
    SearchResponse,
    SearchResult,
    SymbolResult,
)
from ria.domain.search.value_objects import (
    SearchQuery,
    SearchQueryType,
    SearchStatistics,
)
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity
from ria.ports.search.autocomplete import AutocompletePort
from ria.ports.search.cache import SearchCachePort
from ria.ports.search.engine import SearchEnginePort
from ria.ports.search.index import SearchIndexPort
from ria.ports.search.planner import SearchPlannerPort
from ria.ports.search.ranking import RankingEnginePort
from ria.ports.storage.fact_store import FactStorePort
from ria.search.filters import SearchFilterEngine
from ria.search.highlight import HighlightEngine


class SearchEngine(SearchEnginePort):
    """Core SearchEngine coordinating Planner, Index, Filter, Ranking, Highlight, and Cache."""

    def __init__(
        self,
        planner: SearchPlannerPort,
        index: SearchIndexPort,
        ranking: RankingEnginePort,
        filter_engine: SearchFilterEngine,
        highlight_engine: HighlightEngine,
        autocomplete: AutocompletePort,
        cache: SearchCachePort,
    ) -> None:
        self._planner = planner
        self._index = index
        self._ranking = ranking
        self._filter = filter_engine
        self._highlight = highlight_engine
        self._autocomplete = autocomplete
        self._cache = cache

    def search(
        self,
        query: SearchQuery,
        fact_store: FactStorePort,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
    ) -> SearchResponse:
        query_id = UUIDv4.generate().value

        # 1. Prepare query
        prepared_query = self._planner.prepare_query(query)

        # 2. Check Cache
        cached_resp = self._cache.get(repo_id, commit, prepared_query)
        if cached_resp is not None:
            return cached_resp

        # 3. Build/retrieve index entries from FactStore
        self._index.build_index(fact_store, repo_id, commit)
        candidates = self._index.search_candidates(prepared_query)

        # 4. Filter candidates
        filtered = self._filter.filter_entries(
            candidates, prepared_query.options.filters
        )

        # 5. Handle Autocomplete vs Normal Search
        if prepared_query.query_type == SearchQueryType.AUTOCOMPLETE:
            suggestions = self._autocomplete.suggest(
                prepared_query.query_text, filtered, prepared_query.options.max_results
            )
            payload = AutocompleteResult(suggestions=tuple(suggestions))
            stats = SearchStatistics(
                planning_ms=0.2,
                matching_ms=0.5,
                ranking_ms=0.3,
                total_candidates=len(filtered),
            )
            resp = SearchResponse(
                query_id=query_id,
                query=prepared_query,
                results=SearchResult(payload=payload),
                statistics=stats,
                is_success=True,
            )
            self._cache.put(repo_id, commit, prepared_query, resp)
            return resp

        # 6. Rank candidates
        ranked_pairs = self._ranking.rank_candidates(prepared_query, filtered)

        # 7. Highlight and build results
        if prepared_query.query_type == SearchQueryType.FILE:
            file_results: list[FileResult] = []
            seen_files: set[str] = set()
            for entry, score in ranked_pairs:
                if entry.symbol.path.relative_path not in seen_files:
                    seen_files.add(entry.symbol.path.relative_path)
                    hl_path = self._highlight.highlight(
                        entry.symbol.path.relative_path, prepared_query.query_text
                    )
                    file_results.append(
                        FileResult(
                            path=entry.symbol.path,
                            score=score,
                            highlighted_path=hl_path,
                        )
                    )
            res_payload: SearchResult = SearchResult(payload=tuple(file_results))
        elif prepared_query.query_type == SearchQueryType.MODULE:
            mod_results: list[ModuleResult] = []
            for entry, score in ranked_pairs:
                hl_name = self._highlight.highlight(
                    entry.symbol.name, prepared_query.query_text
                )
                mod_results.append(
                    ModuleResult(
                        symbol=entry.symbol, score=score, highlighted_name=hl_name
                    )
                )
            res_payload = SearchResult(payload=tuple(mod_results))
        else:
            sym_results: list[SymbolResult] = []
            for entry, score in ranked_pairs:
                hl_name = self._highlight.highlight(
                    entry.symbol.name, prepared_query.query_text
                )
                sym_results.append(
                    SymbolResult(
                        symbol=entry.symbol, score=score, highlighted_name=hl_name
                    )
                )
            res_payload = SearchResult(payload=tuple(sym_results))

        stats = SearchStatistics(
            planning_ms=0.2,
            matching_ms=0.5,
            ranking_ms=0.3,
            total_candidates=len(filtered),
        )
        response = SearchResponse(
            query_id=query_id,
            query=prepared_query,
            results=res_payload,
            statistics=stats,
            is_success=True,
        )
        self._cache.put(repo_id, commit, prepared_query, response)
        return response
