"""Cache invalidation port protocols."""

from typing import Protocol, runtime_checkable

from ria.domain.snapshot.value_objects import CacheInvalidationPlan, IncrementalPlan


@runtime_checkable
class QueryCachePort(Protocol):
    """Minimal cache capability needed by incremental invalidation."""

    def clear(self) -> None:
        """Clear cached query results."""
        ...


@runtime_checkable
class CacheInvalidatorPort(Protocol):
    """Protocol for invalidating query-cache entries after incremental changes."""

    def invalidate(
        self,
        cache: QueryCachePort,
        plan: IncrementalPlan,
    ) -> CacheInvalidationPlan:
        """Perform targeted query cache invalidation."""
        ...
