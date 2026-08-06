"""Query Planner Port Protocol."""

from typing import Protocol, runtime_checkable

from ria.domain.query.entities import Query
from ria.domain.query.value_objects import QueryPlan


@runtime_checkable
class QueryPlannerPort(Protocol):
    """Protocol for converting high-level semantic Queries into executable QueryPlans."""

    def create_plan(self, query: Query) -> QueryPlan:
        """Construct an executable QueryPlan for a semantic Query."""
        ...
