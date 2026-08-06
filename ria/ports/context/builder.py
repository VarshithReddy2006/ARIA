"""Context Builder Port Protocol."""

from typing import Protocol, runtime_checkable

from ria.domain.context.entities import ContextPackage
from ria.domain.context.value_objects import ContextRequest
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity
from ria.ports.query.engine import QueryEnginePort
from ria.ports.search.engine import SearchEnginePort
from ria.ports.storage.fact_store import FactStorePort


@runtime_checkable
class ContextBuilderPort(Protocol):
    """Protocol for high-level ContextBuilder subsystem."""

    def build_context(
        self,
        request: ContextRequest,
        search_engine: SearchEnginePort,
        query_engine: QueryEnginePort,
        fact_store: FactStorePort,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
    ) -> ContextPackage:
        """Assemble ContextPackage for a given ContextRequest."""
        ...
