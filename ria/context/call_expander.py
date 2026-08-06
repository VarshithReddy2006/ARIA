"""Call Graph Expander."""

from collections.abc import Sequence

from ria.domain.context.entities import ContextSnippet
from ria.domain.context.value_objects import Citation, RankingScore
from ria.domain.query import CallHierarchyResult, Query, QueryCriteria, QueryType
from ria.domain.resolution.entities import SemanticSymbol
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity
from ria.ports.query.engine import QueryEnginePort
from ria.ports.storage.fact_store import FactStorePort


class CallExpander:
    """Expander querying call graph relationships via QueryEnginePort."""

    def expand_calls(
        self,
        symbols: Sequence[SemanticSymbol],
        query_engine: QueryEnginePort,
        fact_store: FactStorePort,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
    ) -> Sequence[ContextSnippet]:
        snippets: list[ContextSnippet] = []
        for sym in symbols:
            q_callers = Query(
                query_id="callers_q",
                query_type=QueryType.FIND_CALLERS,
                criteria=QueryCriteria(symbol_moniker=sym.moniker),
            )
            res_callers = query_engine.execute_query(
                q_callers, fact_store, repo_id, commit
            )
            if res_callers.is_success and isinstance(
                res_callers.payload, CallHierarchyResult
            ):
                for idx, call in enumerate(res_callers.payload.calls):
                    cit = Citation(
                        repo_name=repo_id.name,
                        commit_sha=commit.sha,
                        file_path=sym.path,
                        module_name=sym.path.relative_path,
                        symbol_moniker=call.caller_moniker,
                        start_line=call.location.start_line,
                        end_line=call.location.end_line,
                    )
                    content = f"Caller: {call.caller_moniker.value} calls {call.callee_moniker.value}"
                    est_tokens = max(len(content) // 4, 1)
                    score = RankingScore(priority=3, score_value=0.8, category="Caller")
                    snippets.append(
                        ContextSnippet(
                            snippet_id=f"caller_{idx}",
                            content=content,
                            citation=cit,
                            score=score,
                            estimated_tokens=est_tokens,
                        )
                    )

            q_callees = Query(
                query_id="callees_q",
                query_type=QueryType.FIND_CALLEES,
                criteria=QueryCriteria(symbol_moniker=sym.moniker),
            )
            res_callees = query_engine.execute_query(
                q_callees, fact_store, repo_id, commit
            )
            if res_callees.is_success and isinstance(
                res_callees.payload, CallHierarchyResult
            ):
                for idx, call in enumerate(res_callees.payload.calls):
                    cit = Citation(
                        repo_name=repo_id.name,
                        commit_sha=commit.sha,
                        file_path=sym.path,
                        module_name=sym.path.relative_path,
                        symbol_moniker=call.callee_moniker,
                        start_line=call.location.start_line,
                        end_line=call.location.end_line,
                    )
                    content = f"Callee: {call.caller_moniker.value} calls {call.callee_moniker.value}"
                    est_tokens = max(len(content) // 4, 1)
                    score = RankingScore(priority=3, score_value=0.8, category="Callee")
                    snippets.append(
                        ContextSnippet(
                            snippet_id=f"callee_{idx}",
                            content=content,
                            citation=cit,
                            score=score,
                            estimated_tokens=est_tokens,
                        )
                    )

        return tuple(snippets)
