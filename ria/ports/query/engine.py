"""Query Engine Port Protocol."""

from typing import Protocol, runtime_checkable

from ria.domain.query.entities import Query, QueryResult
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity
from ria.ports.storage.fact_store import FactStorePort


@runtime_checkable
class QueryEnginePort(Protocol):
    """Protocol representing high-level semantic Query Engine."""

    def execute_query(
        self,
        query: Query,
        fact_store: FactStorePort,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
    ) -> QueryResult:
        """Process semantic query against FactStore and return QueryResult."""
        ...
