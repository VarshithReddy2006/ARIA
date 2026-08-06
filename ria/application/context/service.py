"""Application Service for Context Builder."""

from typing import Optional

from ria.application.context.dto import BuildContextCommandDTO
from ria.context.dto import ContextResponseDTO
from ria.context.engine import ContextEngine
from ria.domain.context.value_objects import ContextOptions, ContextRequest, TokenBudget
from ria.ports.common.clock import ClockPort
from ria.ports.common.logger import LoggerPort
from ria.ports.common.metrics import MetricsPort
from ria.ports.query.engine import QueryEnginePort
from ria.ports.search.engine import SearchEnginePort
from ria.ports.storage.fact_store import FactStorePort
from ria.ports.sync.registry import RepositoryRegistryPort


class ContextApplicationService:
    """Application Service coordinating repository lookup and ContextEngine assembly."""

    def __init__(
        self,
        context_engine: ContextEngine,
        search_engine: SearchEnginePort,
        query_engine: QueryEnginePort,
        fact_store: FactStorePort,
        registry: RepositoryRegistryPort,
        clock: ClockPort,
        logger: LoggerPort,
        metrics: MetricsPort,
    ) -> None:
        self._engine = context_engine
        self._search = search_engine
        self._query = query_engine
        self._fact_store = fact_store
        self._registry = registry
        self._clock = clock
        self._logger = logger
        self._metrics = metrics

    def build_context(self, dto: BuildContextCommandDTO) -> ContextResponseDTO:
        start_t = self._clock.monotonic_seconds()
        self._logger.info("Executing ContextApplicationService.build_context", repo_id=dto.repo_id)

        st = next((s for s in self._registry.list_all() if s.identity.repo_id.value == dto.repo_id), None)
        if st is None or st.current_commit is None:
            return ContextResponseDTO(
                package_id="none",
                total_sections=0,
                total_snippets=0,
                total_tokens=0,
                content="",
                elapsed_ms=0.0,
                is_success=False,
                error_message=f"Repository '{dto.repo_id}' is not registered or synchronized.",
            )

        try:
            req = ContextRequest(
                question=dto.question,
                options=ContextOptions(token_budget=TokenBudget(max_tokens=dto.max_tokens)),
            )

            package, formatted = self._engine.assemble_and_serialize(
                req,
                self._search,
                self._query,
                self._fact_store,
                st.identity,
                st.current_commit,
                fmt=dto.format,
            )

            elapsed = (self._clock.monotonic_seconds() - start_t) * 1000.0
            self._metrics.record_duration("context_build_ms", elapsed)

            return ContextResponseDTO(
                package_id=package.package_id,
                total_sections=package.metadata.total_sections,
                total_snippets=package.metadata.total_snippets,
                total_tokens=package.metadata.total_tokens,
                content=formatted,
                elapsed_ms=elapsed,
                is_success=True,
            )
        except Exception as err:
            elapsed = (self._clock.monotonic_seconds() - start_t) * 1000.0
            self._logger.error("Context assembly failed", exc=err, repo_id=dto.repo_id)
            return ContextResponseDTO(
                package_id="none",
                total_sections=0,
                total_snippets=0,
                total_tokens=0,
                content="",
                elapsed_ms=elapsed,
                is_success=False,
                error_message=str(err),
            )
