"""Search Index Port Protocol."""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ria.domain.search.value_objects import SearchIndexEntry, SearchQuery
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity
from ria.ports.storage.fact_store import FactStorePort


@runtime_checkable
class SearchIndexPort(Protocol):
    """Protocol for in-memory SearchIndex built from persisted FactStore symbols."""

    def build_index(
        self,
        fact_store: FactStorePort,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
    ) -> int:
        """Construct in-memory search index from FactStore and return total indexed symbols."""
        ...

    def search_candidates(
        self,
        query: SearchQuery,
    ) -> Sequence[SearchIndexEntry]:
        """Return raw candidate entries matching query criteria."""
        ...
