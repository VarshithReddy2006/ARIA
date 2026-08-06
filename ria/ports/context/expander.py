"""Context Expander Port Protocol."""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ria.domain.context.entities import ContextSnippet
from ria.domain.context.value_objects import ExpansionRule
from ria.domain.resolution.entities import SemanticSymbol
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity
from ria.ports.query.engine import QueryEnginePort
from ria.ports.storage.fact_store import FactStorePort


@runtime_checkable
class ContextExpanderPort(Protocol):
    """Protocol for expanding seed symbols into candidate ContextSnippets using QueryEngine and FactStore."""

    def expand(
        self,
        seed_symbols: Sequence[SemanticSymbol],
        rule: ExpansionRule,
        query_engine: QueryEnginePort,
        fact_store: FactStorePort,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
    ) -> Sequence[ContextSnippet]:
        """Expand seed symbols into a candidate sequence of ContextSnippet entities."""
        ...
