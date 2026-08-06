"""Dependency Expander."""

from collections.abc import Sequence

from ria.domain.context.entities import ContextSnippet
from ria.domain.context.value_objects import Citation, RankingScore
from ria.domain.query import DependencyResult, Query, QueryCriteria, QueryType
from ria.domain.resolution.entities import SemanticSymbol
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity
from ria.ports.query.engine import QueryEnginePort
from ria.ports.storage.fact_store import FactStorePort


class DependencyExpander:
    """Expander querying module dependencies via QueryEnginePort."""

    def expand_dependencies(
        self,
        symbols: Sequence[SemanticSymbol],
        query_engine: QueryEnginePort,
        fact_store: FactStorePort,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
    ) -> Sequence[ContextSnippet]:
        snippets: list[ContextSnippet] = []
        for sym in symbols:
            q = Query(query_id="dep_q", query_type=QueryType.DEPENDENCY_ANALYSIS, criteria=QueryCriteria(file_path=sym.path))
            res = query_engine.execute_query(q, fact_store, repo_id, commit)
            if res.is_success and isinstance(res.payload, DependencyResult):
                for idx, rel in enumerate(res.payload.relations):
                    cit = Citation(
                        repo_name=repo_id.name,
                        commit_sha=commit.sha,
                        file_path=sym.path,
                        module_name=sym.path.relative_path,
                        symbol_moniker=rel.source,
                        start_line=rel.location.start_line,
                        end_line=rel.location.end_line,
                    )
                    content = f"Dependency ({rel.kind.value}): {rel.source.value} -> {rel.target.value}"
                    est_tokens = max(len(content) // 4, 1)
                    score = RankingScore(priority=4, score_value=0.7, category="Dependency")
                    snippets.append(ContextSnippet(snippet_id=f"dep_{idx}", content=content, citation=cit, score=score, estimated_tokens=est_tokens))
        return tuple(snippets)
