"""Reference Expander."""

from collections.abc import Sequence

from ria.domain.context.entities import ContextSnippet
from ria.domain.context.value_objects import Citation, RankingScore
from ria.domain.query import Query, QueryCriteria, QueryType, ReferenceResult
from ria.domain.resolution.entities import SemanticSymbol
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity
from ria.ports.query.engine import QueryEnginePort
from ria.ports.storage.fact_store import FactStorePort


class ReferenceExpander:
    """Expander querying symbol references via QueryEnginePort."""

    def expand_references(
        self,
        symbols: Sequence[SemanticSymbol],
        query_engine: QueryEnginePort,
        fact_store: FactStorePort,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
    ) -> Sequence[ContextSnippet]:
        snippets: list[ContextSnippet] = []
        for sym in symbols:
            q = Query(
                query_id="ref_q",
                query_type=QueryType.FIND_REFERENCES,
                criteria=QueryCriteria(symbol_moniker=sym.moniker),
            )
            res = query_engine.execute_query(q, fact_store, repo_id, commit)
            if res.is_success and isinstance(res.payload, ReferenceResult):
                for idx, ref in enumerate(res.payload.references):
                    cit = Citation(
                        repo_name=repo_id.name,
                        commit_sha=commit.sha,
                        file_path=ref.path,
                        module_name=ref.path.relative_path,
                        symbol_moniker=ref.source_moniker,
                        start_line=ref.location.start_line,
                        end_line=ref.location.end_line,
                    )
                    content = f"Reference in {ref.path.relative_path} (L{ref.location.start_line}): {ref.source_moniker.value} -> {ref.target_moniker.value}"
                    est_tokens = max(len(content) // 4, 1)
                    score = RankingScore(
                        priority=2, score_value=0.9, category="Reference"
                    )
                    snippets.append(
                        ContextSnippet(
                            snippet_id=f"ref_{idx}",
                            content=content,
                            citation=cit,
                            score=score,
                            estimated_tokens=est_tokens,
                        )
                    )
        return tuple(snippets)
