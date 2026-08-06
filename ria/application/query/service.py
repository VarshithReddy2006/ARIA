"""Application Service orchestrating semantic queries."""

from typing import Optional

from ria.domain.common.value_objects import UUIDv4
from ria.domain.index.value_objects import FilePath
from ria.domain.query.entities import Query, QueryResult
from ria.domain.query.value_objects import QueryCriteria, QueryType
from ria.domain.resolution.value_objects import SymbolMoniker
from ria.domain.sync.entities import RepositoryState
from ria.ports.common.clock import ClockPort
from ria.ports.common.logger import LoggerPort
from ria.ports.common.metrics import MetricsPort
from ria.ports.query.engine import QueryEnginePort
from ria.ports.storage.fact_store import FactStorePort
from ria.ports.sync.registry import RepositoryRegistryPort


class QueryApplicationService:
    """Application Service coordinating repository state lookup and QueryEngine execution."""

    def __init__(
        self,
        query_engine: QueryEnginePort,
        fact_store: FactStorePort,
        registry: RepositoryRegistryPort,
        clock: ClockPort,
        logger: LoggerPort,
        metrics: MetricsPort,
    ) -> None:
        self._engine = query_engine
        self._fact_store = fact_store
        self._registry = registry
        self._clock = clock
        self._logger = logger
        self._metrics = metrics

    def _get_active_repo_and_commit(
        self, repo_id_str: str
    ) -> tuple[Optional[RepositoryState], Optional[QueryResult]]:
        for st in self._registry.list_all():
            if st.identity.repo_id.value == repo_id_str:
                if st.current_commit is None:
                    return None, None
                return st, None
        return None, None

    def find_definition(
        self,
        repo_id_str: str,
        symbol_moniker: Optional[str] = None,
        symbol_name: Optional[str] = None,
    ) -> QueryResult:
        st, err_res = self._get_active_repo_and_commit(repo_id_str)
        if st is None or st.current_commit is None:
            raise ValueError(
                f"Repository '{repo_id_str}' is not registered or synchronized."
            )

        criteria = QueryCriteria(
            symbol_moniker=SymbolMoniker(value=symbol_moniker)
            if symbol_moniker
            else None,
            symbol_name=symbol_name,
        )
        query = Query(
            query_id=UUIDv4.generate().value,
            query_type=QueryType.GO_TO_DEFINITION,
            criteria=criteria,
        )
        return self._engine.execute_query(
            query, self._fact_store, st.identity, st.current_commit
        )

    def find_references(self, repo_id_str: str, symbol_moniker: str) -> QueryResult:
        st, _ = self._get_active_repo_and_commit(repo_id_str)
        if st is None or st.current_commit is None:
            raise ValueError(
                f"Repository '{repo_id_str}' is not registered or synchronized."
            )

        criteria = QueryCriteria(symbol_moniker=SymbolMoniker(value=symbol_moniker))
        query = Query(
            query_id=UUIDv4.generate().value,
            query_type=QueryType.FIND_REFERENCES,
            criteria=criteria,
        )
        return self._engine.execute_query(
            query, self._fact_store, st.identity, st.current_commit
        )

    def find_call_hierarchy(
        self, repo_id_str: str, symbol_moniker: str, is_callers: bool = True
    ) -> QueryResult:
        st, _ = self._get_active_repo_and_commit(repo_id_str)
        if st is None or st.current_commit is None:
            raise ValueError(
                f"Repository '{repo_id_str}' is not registered or synchronized."
            )

        qtype = QueryType.FIND_CALLERS if is_callers else QueryType.FIND_CALLEES
        criteria = QueryCriteria(symbol_moniker=SymbolMoniker(value=symbol_moniker))
        query = Query(
            query_id=UUIDv4.generate().value,
            query_type=qtype,
            criteria=criteria,
        )
        return self._engine.execute_query(
            query, self._fact_store, st.identity, st.current_commit
        )

    def search_symbols(
        self, repo_id_str: str, query_name: str, max_results: int = 50
    ) -> QueryResult:
        st, _ = self._get_active_repo_and_commit(repo_id_str)
        if st is None or st.current_commit is None:
            raise ValueError(
                f"Repository '{repo_id_str}' is not registered or synchronized."
            )

        criteria = QueryCriteria(symbol_name=query_name, max_results=max_results)
        query = Query(
            query_id=UUIDv4.generate().value,
            query_type=QueryType.SYMBOL_SEARCH,
            criteria=criteria,
        )
        return self._engine.execute_query(
            query, self._fact_store, st.identity, st.current_commit
        )

    def analyze_dependencies(
        self, repo_id_str: str, file_path_str: Optional[str] = None
    ) -> QueryResult:
        st, _ = self._get_active_repo_and_commit(repo_id_str)
        if st is None or st.current_commit is None:
            raise ValueError(
                f"Repository '{repo_id_str}' is not registered or synchronized."
            )

        criteria = QueryCriteria(
            file_path=FilePath(relative_path=file_path_str) if file_path_str else None
        )
        query = Query(
            query_id=UUIDv4.generate().value,
            query_type=QueryType.DEPENDENCY_ANALYSIS,
            criteria=criteria,
        )
        return self._engine.execute_query(
            query, self._fact_store, st.identity, st.current_commit
        )
