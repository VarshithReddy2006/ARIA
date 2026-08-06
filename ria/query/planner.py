"""Query Planner implementation."""

from ria.domain.query.entities import Query
from ria.domain.query.value_objects import QueryPlan
from ria.ports.query.planner import QueryPlannerPort


class QueryPlanner(QueryPlannerPort):
    """Planner transforming high-level semantic Query entities into logical QueryPlans."""

    def create_plan(self, query: Query) -> QueryPlan:
        """Construct immutable QueryPlan."""
        return QueryPlan(
            query_id=query.query_id,
            query_type=query.query_type,
            criteria=query.criteria,
        )
