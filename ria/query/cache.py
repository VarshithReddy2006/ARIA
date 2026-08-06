"""Optional Query Cache abstraction."""

from typing import Dict, Optional, Tuple

from ria.domain.query.entities import QueryResult
from ria.domain.query.value_objects import QueryPlan
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity


class QueryCache:
    """In-memory cache for storing and retrieving QueryResults."""

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled
        self._cache: Dict[Tuple[str, str, str, str], QueryResult] = {}

    def _make_key(
        self,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
        plan: QueryPlan,
    ) -> Tuple[str, str, str, str]:
        criteria_str = (
            f"{plan.criteria.symbol_moniker.value if plan.criteria.symbol_moniker else ''}:"
            f"{plan.criteria.symbol_name or ''}:"
            f"{plan.criteria.file_path.relative_path if plan.criteria.file_path else ''}:"
            f"{plan.criteria.max_results}"
        )
        return (repo_id.repo_id.value, commit.sha, plan.query_type.value, criteria_str)

    def get(
        self,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
        plan: QueryPlan,
    ) -> Optional[QueryResult]:
        if not self._enabled:
            return None
        key = self._make_key(repo_id, commit, plan)
        return self._cache.get(key)

    def put(
        self,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
        plan: QueryPlan,
        result: QueryResult,
    ) -> None:
        if not self._enabled:
            return
        key = self._make_key(repo_id, commit, plan)
        self._cache[key] = result

    def clear(self) -> None:
        self._cache.clear()
