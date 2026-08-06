"""Context Expander implementing ContextExpanderPort."""

from collections.abc import Sequence

from ria.context.call_expander import CallExpander
from ria.context.dependency_expander import DependencyExpander
from ria.context.reference_expander import ReferenceExpander
from ria.domain.context.entities import ContextSnippet
from ria.domain.context.value_objects import Citation, ExpansionRule, RankingScore
from ria.domain.resolution.entities import SemanticSymbol
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity
from ria.ports.context.expander import ContextExpanderPort
from ria.ports.query.engine import QueryEnginePort
from ria.ports.storage.fact_store import FactStorePort


class ContextExpander(ContextExpanderPort):
    """Expander coordinating definition, reference, call, and dependency expansion."""

    def __init__(
        self,
        ref_expander: ReferenceExpander,
        call_expander: CallExpander,
        dep_expander: DependencyExpander,
    ) -> None:
        self._ref = ref_expander
        self._call = call_expander
        self._dep = dep_expander

    def expand(
        self,
        seed_symbols: Sequence[SemanticSymbol],
        rule: ExpansionRule,
        query_engine: QueryEnginePort,
        fact_store: FactStorePort,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
    ) -> Sequence[ContextSnippet]:
        snippets: list[ContextSnippet] = []

        # 1. Definition Expansion (Priority 1)
        for idx, sym in enumerate(seed_symbols):
            cit = Citation(
                repo_name=repo_id.name,
                commit_sha=commit.sha,
                file_path=sym.path,
                module_name=sym.path.relative_path,
                symbol_moniker=sym.moniker,
                start_line=sym.location.start_line,
                end_line=sym.location.end_line,
            )
            content = f"Definition of {sym.kind.value} '{sym.name}' ({sym.qualified_name.dotted_path}) in {sym.path.relative_path}:L{sym.location.start_line}"
            est_tokens = max(len(content) // 4, 1)
            score = RankingScore(priority=1, score_value=1.0, category="Definition")
            snippets.append(
                ContextSnippet(
                    snippet_id=f"def_{idx}",
                    content=content,
                    citation=cit,
                    score=score,
                    estimated_tokens=est_tokens,
                )
            )

        # 2. Reference Expansion (Priority 2)
        ref_snips = self._ref.expand_references(
            seed_symbols, query_engine, fact_store, repo_id, commit
        )
        snippets.extend(ref_snips)

        # 3. Call Graph Expansion (Priority 3)
        if rule.include_callers or rule.include_callees:
            call_snips = self._call.expand_calls(
                seed_symbols, query_engine, fact_store, repo_id, commit
            )
            snippets.extend(call_snips)

        # 4. Dependency Expansion (Priority 4)
        if rule.include_dependencies:
            dep_snips = self._dep.expand_dependencies(
                seed_symbols, query_engine, fact_store, repo_id, commit
            )
            snippets.extend(dep_snips)

        return tuple(snippets)
