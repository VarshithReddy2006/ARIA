"""Incremental Scheduler Port Protocol."""

from typing import Protocol, runtime_checkable

from ria.domain.snapshot.value_objects import IncrementalPlan


@runtime_checkable
class IncrementalSchedulerPort(Protocol):
    """Protocol orchestrating incremental execution across IndexPipeline, ResolutionEngine, FactStore, and QueryCache."""

    def execute_plan(
        self,
        plan: IncrementalPlan,
    ) -> bool:
        """Execute incremental reindexing plan."""
        ...
