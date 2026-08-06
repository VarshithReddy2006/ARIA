"""Application Service orchestrating indexing, symbol resolution, and FactStore persistence."""

from typing import Optional

from ria.application.index import ExecutePipelineCommand, IndexPipeline
from ria.application.resolution.dto import FactSummaryDTO, ResolveAndStoreCommand
from ria.domain.sync.entities import RepositoryState
from ria.ports.common.clock import ClockPort
from ria.ports.common.logger import LoggerPort
from ria.ports.common.metrics import MetricsPort
from ria.ports.resolution.resolver import ResolutionEnginePort
from ria.ports.storage.fact_store import FactStorePort
from ria.ports.sync.registry import RepositoryRegistryPort


class ResolutionApplicationService:
    """Application service coordinating IndexPipeline, ResolutionEngine, and FactStore persistence."""

    def __init__(
        self,
        index_pipeline: IndexPipeline,
        resolution_engine: ResolutionEnginePort,
        fact_store: FactStorePort,
        registry: RepositoryRegistryPort,
        clock: ClockPort,
        logger: LoggerPort,
        metrics: MetricsPort,
    ) -> None:
        self._index_pipeline = index_pipeline
        self._engine = resolution_engine
        self._fact_store = fact_store
        self._registry = registry
        self._clock = clock
        self._logger = logger
        self._metrics = metrics

    def resolve_and_store(self, command: ResolveAndStoreCommand) -> FactSummaryDTO:
        """Execute indexing, resolve symbols, and save facts into FactStore."""
        start_time = self._clock.monotonic_seconds()
        self._logger.info("Executing ResolutionApplicationService", repo_id=command.repo_id)

        # Lookup state
        target_state: Optional[RepositoryState] = None
        for st in self._registry.list_all():
            if st.identity.repo_id.value == command.repo_id:
                target_state = st
                break

        if target_state is None or target_state.current_commit is None:
            return FactSummaryDTO(
                repo_id=command.repo_id,
                commit_sha=command.commit_sha or "unknown",
                total_symbols=0,
                total_definitions=0,
                total_references=0,
                total_calls=0,
                total_imports=0,
                total_inheritance=0,
                is_success=False,
                error_message=f"Repository '{command.repo_id}' is not registered or synchronized.",
            )

        repo_identity = target_state.identity
        commit = target_state.current_commit

        try:
            # 1. Execute Index Pipeline
            index_batch, pipe_dto = self._index_pipeline.execute(ExecutePipelineCommand(repo_id=command.repo_id))

            # 2. Execute Resolution Engine
            fact_set = self._engine.resolve_batch(index_batch)

            # 3. Persist to FactStore
            self._fact_store.save_fact_set(repo_identity, commit, fact_set)

            elapsed = self._clock.monotonic_seconds() - start_time
            self._metrics.record_duration("resolution_and_store_seconds", elapsed)
            self._metrics.increment_counter("resolution_success_total")

            return FactSummaryDTO(
                repo_id=command.repo_id,
                commit_sha=commit.sha,
                total_symbols=len(fact_set.symbols),
                total_definitions=len(fact_set.definitions),
                total_references=len(fact_set.references),
                total_calls=len(fact_set.calls),
                total_imports=len(fact_set.imports),
                total_inheritance=len(fact_set.inheritance),
                is_success=True,
            )
        except Exception as err:
            self._metrics.increment_counter("resolution_failure_total")
            self._logger.error("Resolution and store pipeline failed", exc=err, repo_id=command.repo_id)
            return FactSummaryDTO(
                repo_id=command.repo_id,
                commit_sha=commit.sha,
                total_symbols=0,
                total_definitions=0,
                total_references=0,
                total_calls=0,
                total_imports=0,
                total_inheritance=0,
                is_success=False,
                error_message=str(err),
            )
