"""Search Cache implementing SearchCachePort."""

from typing import Dict, Optional, Tuple

from ria.domain.search.entities import SearchResponse
from ria.domain.search.value_objects import SearchQuery
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity
from ria.ports.search.cache import SearchCachePort


class SearchCache(SearchCachePort):
    """In-memory SearchCache for storing and invalidating search results."""

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled
        self._cache: Dict[Tuple[str, str, str, str], SearchResponse] = {}

    def _make_key(
        self,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
        query: SearchQuery,
    ) -> Tuple[str, str, str, str]:
        return (
            repo_id.repo_id.value,
            commit.sha,
            query.query_type.value,
            query.query_text,
        )

    def get(
        self,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
        query: SearchQuery,
    ) -> Optional[SearchResponse]:
        if not self._enabled:
            return None
        key = self._make_key(repo_id, commit, query)
        return self._cache.get(key)

    def put(
        self,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
        query: SearchQuery,
        response: SearchResponse,
    ) -> None:
        if not self._enabled:
            return
        key = self._make_key(repo_id, commit, query)
        self._cache[key] = response

    def invalidate(
        self,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
    ) -> None:
        prefix = (repo_id.repo_id.value, commit.sha)
        to_del = [k for k in self._cache if (k[0], k[1]) == prefix]
        for k in to_del:
            del self._cache[k]
