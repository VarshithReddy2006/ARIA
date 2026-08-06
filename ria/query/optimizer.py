"""Query Optimizer."""

from ria.domain.query.value_objects import QueryCriteria, QueryPlan


class QueryOptimizer:
    """Optimizer validating and optimizing QueryPlan criteria before execution."""

    def optimize_plan(self, plan: QueryPlan) -> QueryPlan:
        """Sanitize max_results limit and criteria."""
        bounded_max = min(max(plan.criteria.max_results, 1), 1000)
        opt_criteria = QueryCriteria(
            symbol_moniker=plan.criteria.symbol_moniker,
            symbol_name=plan.criteria.symbol_name.strip() if plan.criteria.symbol_name else None,
            file_path=plan.criteria.file_path,
            max_results=bounded_max,
        )
        return QueryPlan(
            query_id=plan.query_id,
            query_type=plan.query_type,
            criteria=opt_criteria,
        )
