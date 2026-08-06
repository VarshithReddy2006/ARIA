"""Search Planner implementing SearchPlannerPort."""

from ria.domain.search.value_objects import SearchOptions, SearchQuery
from ria.ports.search.planner import SearchPlannerPort


class SearchPlanner(SearchPlannerPort):
    """Planner preparing and sanitizing SearchQuery objects before index evaluation."""

    def prepare_query(self, query: SearchQuery) -> SearchQuery:
        """Clean query text and construct bounded SearchOptions."""
        sanitized_text = query.query_text.strip()
        bounded_max = min(max(query.options.max_results, 1), 500)
        options = SearchOptions(
            filters=query.options.filters,
            scope=query.options.scope,
            max_results=bounded_max,
        )
        return SearchQuery(
            query_text=sanitized_text,
            query_type=query.query_type,
            options=options,
        )
