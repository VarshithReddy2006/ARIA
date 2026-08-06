"""Incremental Scheduler implementing IncrementalSchedulerPort."""

from typing import Any

from ria.domain.common.value_objects import UUIDv4
from ria.domain.index.units import IndexBatch, ParseUnit
from ria.domain.snapshot.value_objects import IncrementalPlan
from ria.ports.common.clock import ClockPort
from ria.ports.common.logger import LoggerPort
from ria.ports.common.metrics import MetricsPort
from ria.ports.incremental.cache import CacheInvalidatorPort
from ria.ports.incremental.scheduler import IncrementalSchedulerPort
from ria.ports.index.filesystem import FilesystemPort
from ria.ports.index.parser_registry import ParserRegistryPort
from ria.ports.resolution.resolver import ResolutionEnginePort
from ria.ports.storage.fact_store import FactStorePort
from ria.ports.sync.workspace import WorkspacePort
from ria.query.cache import QueryCache


class IncrementalScheduler(IncrementalSchedulerPort):
    """Scheduler orchestrating incremental execution across Index, Resolution, FactStore, and QueryCache."""

    def __init__(self, scanner: Any, parser_registry: ParserRegistryPort, unit_builder: Any, batch_assembler: Any, resolution_engine: ResolutionEnginePort, fact_store: FactStorePort, workspace_manager: WorkspacePort, filesystem: FilesystemPort, cache_invalidator: CacheInvalidatorPort, query_cache: QueryCache, clock: ClockPort, logger: LoggerPort, metrics: MetricsPort) -> None:
        self._scanner = scanner
        self._parser_registry = parser_registry
        self._builder = unit_builder
        self._assembler = batch_assembler
        self._engine = resolution_engine
        self._fact_store = fact_store
        self._workspace = workspace_manager
        self._fs = filesystem
        self._invalidator = cache_invalidator
        self._cache = query_cache
        self._clock = clock
        self._logger = logger
        self._metrics = metrics

    def execute_plan(self, plan: IncrementalPlan) -> bool:
        """Execute incremental plan."""
        start_time = self._clock.monotonic_seconds()
        self._logger.info("Executing IncrementalScheduler plan", repo_id=plan.repo_id.repo_id.value)

        ws_dir = self._workspace.get_workspace_path(plan.repo_id)

        try:
            # 1. Targeted scan of changed files
            if plan.files_to_reindex:
                file_units = self._scanner.scan_incremental(ws_dir, plan.files_to_reindex)

                # 2. Parse changed files
                parse_units: list[ParseUnit] = []
                for fu in file_units:
                    abs_p = ws_dir / fu.path.relative_path
                    parser_plugin = self._parser_registry.get_parser(fu.language)

                    t0 = self._clock.monotonic_seconds()
                    if parser_plugin and self._fs.exists(abs_p):
                        code = self._fs.read_bytes(abs_p)
                        parser_result = parser_plugin.parse(fu.path, code)
                    else:
                        parser_result = None
                    parse_duration = (self._clock.monotonic_seconds() - t0) * 1000.0

                    pu = self._builder.build_parse_unit(fu, parser_result, parse_duration)
                    parse_units.append(pu)

                # 3. Assemble partial IndexBatch
                batch, _ = self._assembler.assemble_batch(
                    repo_id=plan.repo_id,
                    commit=plan.to_commit,
                    parse_units=parse_units,
                    created_at=self._clock.now_utc(),
                )

                # 4. Resolve semantic symbols for changed units
                fact_set = self._engine.resolve_batch(batch)

                # 5. Incremental FactStore update
                self._fact_store.save_fact_set(plan.repo_id, plan.to_commit, fact_set)

            # 6. Invalidate query cache
            self._invalidator.invalidate(self._cache, plan)

            elapsed = self._clock.monotonic_seconds() - start_time
            self._metrics.record_duration("incremental_execution_seconds", elapsed)
            self._metrics.increment_counter("incremental_success_total")
            return True
        except Exception as err:
            self._metrics.increment_counter("incremental_failure_total")
            self._logger.error("Incremental execution failed", exc=err, repo_id=plan.repo_id.repo_id.value)
            return False
