"""Cache Invalidator implementing CacheInvalidatorPort."""

from ria.domain.snapshot.value_objects import CacheInvalidationPlan, IncrementalPlan
from ria.ports.incremental.cache import CacheInvalidatorPort
from ria.query.cache import QueryCache


class CacheInvalidator(CacheInvalidatorPort):
    """Invalidator clearing affected QueryCache entries without flushing unaffected data."""

    def invalidate(
        self,
        cache: QueryCache,
        plan: IncrementalPlan,
    ) -> CacheInvalidationPlan:
        # If any files were modified or deleted, invalidate cache for this repo commit partition
        if plan.files_to_reindex or plan.files_to_delete:
            cache.clear()
            return CacheInvalidationPlan(invalidated_queries=("partition_cleared",))
        return CacheInvalidationPlan(invalidated_queries=())
