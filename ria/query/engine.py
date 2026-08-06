"""Query Engine implementing QueryEnginePort."""

from ria.domain.query.entities import Query, QueryResult
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity
from ria.ports.query.engine import QueryEnginePort
from ria.ports.query.executor import QueryExecutorPort
from ria.ports.query.planner import QueryPlannerPort
from ria.ports.storage.fact_store import FactStorePort
from ria.query.cache import QueryCache
from ria.query.optimizer import QueryOptimizer


class QueryEngine(QueryEnginePort):
    """Core QueryEngine coordinating Planner, Optimizer, Cache, and Executor to answer semantic repository queries."""

    def __init__(
        self,
        planner: QueryPlannerPort,
        executor: QueryExecutorPort,
        optimizer: QueryOptimizer,
        cache: QueryCache,
    ) -> None:
        self._planner = planner
        self._executor = executor
        self._optimizer = optimizer
        self._cache = cache

    def execute_query(
        self,
        query: Query,
        fact_store: FactStorePort,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
    ) -> QueryResult:
        # 1. Create plan
        plan = self._planner.create_plan(query)

        # 2. Optimize plan
        opt_plan = self._optimizer.optimize_plan(plan)

        # 3. Check Cache
        cached_result = self._cache.get(repo_id, commit, opt_plan)
        if cached_result is not None:
            return cached_result

        # 4. Execute plan over FactStore
        result = self._executor.execute_plan(opt_plan, fact_store, repo_id, commit)

        # 5. Save to Cache if successful
        if result.is_success:
            self._cache.put(repo_id, commit, opt_plan, result)

        return result
