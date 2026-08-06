"""Context Builder implementing ContextBuilderPort."""

import time

from ria.context.deduplicator import Deduplicator
from ria.domain.common.value_objects import UUIDv4
from ria.domain.context.entities import (
    ContextMetadata,
    ContextPackage,
    ContextSection,
    ContextSnippet,
)
from ria.domain.context.value_objects import ContextRequest, ContextStatistics
from ria.domain.resolution.entities import SemanticSymbol
from ria.domain.search import SearchQuery, SearchQueryType, SymbolResult
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity
from ria.ports.context.builder import ContextBuilderPort
from ria.ports.context.expander import ContextExpanderPort
from ria.ports.context.optimizer import BudgetOptimizerPort
from ria.ports.context.ranking import RankingPort
from ria.ports.query.engine import QueryEnginePort
from ria.ports.search.engine import SearchEnginePort
from ria.ports.storage.fact_store import FactStorePort


class ContextBuilder(ContextBuilderPort):
    """Core ContextBuilder coordinating Search, Expander, Ranker, Deduplicator, and BudgetOptimizer."""

    def __init__(
        self,
        expander: ContextExpanderPort,
        ranker: RankingPort,
        deduplicator: Deduplicator,
        optimizer: BudgetOptimizerPort,
    ) -> None:
        self._expander = expander
        self._ranker = ranker
        self._deduplicator = deduplicator
        self._optimizer = optimizer

    def build_context(
        self,
        request: ContextRequest,
        search_engine: SearchEnginePort,
        query_engine: QueryEnginePort,
        fact_store: FactStorePort,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
    ) -> ContextPackage:
        t_start = time.perf_counter()

        # 1. Search for seed symbols matching question
        search_q = SearchQuery(query_text=request.question, query_type=SearchQueryType.PREFIX)
        search_resp = search_engine.search(search_q, fact_store, repo_id, commit)

        seed_symbols: list[SemanticSymbol] = []
        if search_resp.is_success and isinstance(search_resp.results.payload, tuple):
            for res in search_resp.results.payload:
                if isinstance(res, SymbolResult):
                    seed_symbols.append(res.symbol)

        # Fallback to get all symbols if search returned empty
        if not seed_symbols:
            seed_symbols = list(fact_store.get_symbols(repo_id, commit)[:5])

        # 2. Expand seed symbols into candidate snippets
        t_exp = time.perf_counter()
        raw_snippets = self._expander.expand(
            seed_symbols,
            request.options.expansion_rule,
            query_engine,
            fact_store,
            repo_id,
            commit,
        )
        exp_ms = (time.perf_counter() - t_exp) * 1000.0

        # 3. Rank snippets
        t_rank = time.perf_counter()
        ranked = self._ranker.rank_snippets(raw_snippets)
        rank_ms = (time.perf_counter() - t_rank) * 1000.0

        # 4. Deduplicate snippets
        t_dedup = time.perf_counter()
        deduped = self._deduplicator.deduplicate(ranked)
        dedup_ms = (time.perf_counter() - t_dedup) * 1000.0

        # 5. Optimize token budget
        t_opt = time.perf_counter()
        final_snippets = self._optimizer.optimize_budget(deduped, request.options.token_budget)
        opt_ms = (time.perf_counter() - t_opt) * 1000.0

        # Group by category sections
        sec_map: dict[str, list[ContextSnippet]] = {}
        total_tokens = 0
        for snip in final_snippets:
            cat = snip.score.category
            if cat not in sec_map:
                sec_map[cat] = []
            sec_map[cat].append(snip)
            total_tokens += snip.estimated_tokens

        sections = tuple(ContextSection(title=cat, snippets=tuple(snips)) for cat, snips in sec_map.items())

        stats = ContextStatistics(
            expansion_ms=exp_ms,
            ranking_ms=rank_ms,
            deduplication_ms=dedup_ms,
            optimization_ms=opt_ms,
            total_snippets=len(final_snippets),
            total_tokens=total_tokens,
        )
        meta = ContextMetadata(
            total_sections=len(sections),
            total_snippets=len(final_snippets),
            total_tokens=total_tokens,
            token_budget=request.options.token_budget.max_tokens,
        )

        return ContextPackage(
            package_id=UUIDv4.generate().value,
            question=request.question,
            sections=sections,
            references=(),
            metadata=meta,
            statistics=stats,
        )
