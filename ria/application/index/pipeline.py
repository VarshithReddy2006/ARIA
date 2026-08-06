"""Index Pipeline Orchestrator."""

from pathlib import Path
from typing import Optional

from ria.application.index.assembler import IndexBatchAssembler
from ria.application.index.builder import IndexUnitBuilder
from ria.application.index.dto import ExecutePipelineCommand, PipelineResultDTO
from ria.application.index.exceptions import PipelineException
from ria.application.index.scanner import RepositoryScanner
from ria.domain.common.value_objects import UUIDv4
from ria.domain.index.units import IndexBatch, ParseUnit
from ria.domain.sync.entities import RepositoryState
from ria.ports.common.clock import ClockPort
from ria.ports.common.logger import LoggerPort
from ria.ports.common.metrics import MetricsPort
from ria.ports.index.filesystem import FilesystemPort
from ria.ports.index.parser_registry import ParserRegistryPort
from ria.ports.sync.registry import RepositoryRegistryPort
from ria.ports.sync.workspace import WorkspacePort


class IndexPipeline:
    """Orchestrator coordinating workspace scanning, parser plugin selection, parsing, and IndexBatch assembly."""

    def __init__(
        self,
        scanner: RepositoryScanner,
        parser_registry: ParserRegistryPort,
        unit_builder: IndexUnitBuilder,
        batch_assembler: IndexBatchAssembler,
        registry: RepositoryRegistryPort,
        workspace_manager: WorkspacePort,
        filesystem: FilesystemPort,
        clock: ClockPort,
        logger: LoggerPort,
        metrics: MetricsPort,
    ) -> None:
        self._scanner = scanner
        self._parser_registry = parser_registry
        self._builder = unit_builder
        self._assembler = batch_assembler
        self._registry = registry
        self._workspace_manager = workspace_manager
        self._fs = filesystem
        self._clock = clock
        self._logger = logger
        self._metrics = metrics

    def execute(self, command: ExecutePipelineCommand) -> tuple[IndexBatch, PipelineResultDTO]:
        """Execute full indexing pipeline for repository."""
        start_time = self._clock.monotonic_seconds()
        self._logger.info("Executing IndexPipeline", repo_id=command.repo_id)

        # Lookup state
        target_state: Optional[RepositoryState] = None
        for st in self._registry.list_all():
            if st.identity.repo_id.value == command.repo_id:
                target_state = st
                break

        if target_state is None:
            raise PipelineException(f"Repository with ID '{command.repo_id}' is not registered.")
        if target_state.current_commit is None:
            raise PipelineException(f"Repository '{command.repo_id}' is not synchronized (missing current commit).")

        repo_identity = target_state.identity
        commit = target_state.current_commit
        workspace_dir = self._workspace_manager.get_workspace_path(repo_identity)

        if not self._fs.exists(workspace_dir):
            raise PipelineException(f"Workspace directory for repository '{command.repo_id}' does not exist.")

        try:
            # 1. Scan files
            file_units = self._scanner.scan_repository(workspace_dir)
            self._logger.info("Discovered files during scan", count=len(file_units), repo_id=command.repo_id)

            # 2. Parse files
            parse_units: list[ParseUnit] = []
            for fu in file_units:
                abs_p = workspace_dir / fu.path.relative_path
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

            # 3. Assemble IndexBatch
            batch, manifest = self._assembler.assemble_batch(
                repo_id=repo_identity,
                commit=commit,
                parse_units=parse_units,
                created_at=self._clock.now_utc(),
            )

            elapsed = self._clock.monotonic_seconds() - start_time
            self._metrics.record_duration("pipeline_execution_seconds", elapsed)
            self._metrics.increment_counter("pipeline_success_total")

            result_dto = PipelineResultDTO(
                batch_id=batch.batch_id.value,
                repo_id=command.repo_id,
                commit_sha=commit.sha,
                total_files_discovered=manifest.total_files,
                total_files_parsed=manifest.total_parsed,
                total_files_failed=manifest.total_failed,
                elapsed_seconds=elapsed,
                is_success=True,
            )

            return batch, result_dto
        except Exception as err:
            self._metrics.increment_counter("pipeline_failure_total")
            self._logger.error("IndexPipeline execution failed", exc=err, repo_id=command.repo_id)
            raise PipelineException(f"IndexPipeline failed for repository '{command.repo_id}': {err}") from err
