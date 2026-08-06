"""Search Cache Port Protocol."""

from typing import Optional, Protocol, runtime_checkable

from ria.domain.search.entities import SearchResponse
from ria.domain.search.value_objects import SearchQuery
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity


@runtime_checkable
class SearchCachePort(Protocol):
    """Protocol for caching and invalidating SearchResponse objects."""

    def get(
        self,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
        query: SearchQuery,
    ) -> Optional[SearchResponse]:
        """Retrieve cached SearchResponse."""
        ...

    def put(
        self,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
        query: SearchQuery,
        response: SearchResponse,
    ) -> None:
        """Cache SearchResponse."""
        ...

    def invalidate(
        self,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
    ) -> None:
        """Invalidate cache entries for a repository commit partition."""
        ...
