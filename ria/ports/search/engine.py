"""Search Engine Port Protocol."""

from typing import Protocol, runtime_checkable

from ria.domain.search.entities import SearchResponse
from ria.domain.search.value_objects import SearchQuery
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity
from ria.ports.storage.fact_store import FactStorePort


@runtime_checkable
class SearchEnginePort(Protocol):
    """Protocol for high-level SearchEngine subsystem."""

    def search(
        self,
        query: SearchQuery,
        fact_store: FactStorePort,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
    ) -> SearchResponse:
        """Process SearchQuery over FactStore and return SearchResponse."""
        ...
