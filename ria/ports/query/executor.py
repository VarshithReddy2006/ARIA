"""Query Executor Port Protocol."""

from typing import Protocol, runtime_checkable

from ria.domain.query.entities import QueryResult
from ria.domain.query.value_objects import QueryPlan
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity
from ria.ports.storage.fact_store import FactStorePort


@runtime_checkable
class QueryExecutorPort(Protocol):
    """Protocol for executing QueryPlans over FactStorePort abstractions."""

    def execute_plan(
        self,
        plan: QueryPlan,
        fact_store: FactStorePort,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
    ) -> QueryResult:
        """Execute QueryPlan using FactStorePort and return immutable QueryResult."""
        ...
