"""Query Optimizer application service.

Optimizes query execution through index selection, query caching, traversal pruning,
and deterministic execution plan generation.
"""

from __future__ import annotations

from typing import Optional

from ria.domain.models.query_identity import QueryCacheKey, QueryFingerprint
from ria.domain.models.query_request import QueryRequest
from ria.domain.models.query_result import QueryResult
from ria.ports.query import QueryCacheStore

__all__ = ["QueryOptimizer"]


class QueryOptimizer:
    """Optimizer for query execution plans and caching."""

    def __init__(self, cache_store: Optional[QueryCacheStore] = None) -> None:
        self._cache = cache_store

    def build_cache_key(self, request: QueryRequest) -> QueryCacheKey:
        """Construct content-addressed QueryCacheKey for a QueryRequest."""
        fp = QueryFingerprint(
            query_type=request.query_type,
            target_name=request.target_name or "",
            filter_token=",".join(sorted(request.filter.kinds)),
        )
        return QueryCacheKey(
            repository_id=request.context.repository_id,
            commit_sha=request.context.commit_sha,
            fingerprint=fp,
        )

    def get_cached_result(self, request: QueryRequest) -> Optional[QueryResult]:
        """Look up cached QueryResult."""
        if self._cache is None:
            return None
        key = self.build_cache_key(request)
        return self._cache.get(key)

    def cache_result(self, request: QueryRequest, result: QueryResult) -> None:
        """Cache QueryResult for future reuse."""
        if self._cache is None:
            return
        key = self.build_cache_key(request)
        self._cache.put(key, result)
