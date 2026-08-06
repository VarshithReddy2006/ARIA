"""Search Planner Port Protocol."""

from typing import Protocol, runtime_checkable

from ria.domain.search.value_objects import SearchQuery


@runtime_checkable
class SearchPlannerPort(Protocol):
    """Protocol constructing execution plan for SearchQuery."""

    def prepare_query(self, query: SearchQuery) -> SearchQuery:
        """Sanitize and prepare SearchQuery for index evaluation."""
        ...
