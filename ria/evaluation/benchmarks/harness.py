"""Benchmark Runner Harness."""

from pathlib import Path
from typing import Tuple

from ria.application.index import (
    ExecutePipelineCommand,
    FileDiscovery,
    IndexBatchAssembler,
    IndexPipeline,
    IndexUnitBuilder,
    LanguageDetection,
    RepositoryScanner,
)
from ria.application.sync import (
    RegisterRepositoryCommand,
    RegisterRepositoryUseCase,
    SynchronizeRepositoryCommand,
    SynchronizeRepositoryUseCase,
)
from ria.config import Container, Settings
from ria.domain.index.units import IndexBatch
from ria.evaluation.datasets.manifest import BenchmarkDatasetSpec
from ria.evaluation.metrics.collector import BenchmarkResult, PerformanceCollector
from ria.plugins import (
    PluginLoader,
    PluginRegistry,
    JavaScriptTreeSitterPlugin,
    PythonTreeSitterPlugin,
    TypeScriptTreeSitterPlugin,
)


class BenchmarkHarness:
    """Automated benchmark harness measuring stage-by-stage pipeline metrics."""

    def __init__(self, work_dir: Path) -> None:
        self._work_dir = work_dir
        self._settings = Settings.create_testing(work_dir)
        self._container = Container.create(self._settings)

    def run_benchmark(
        self, dataset: BenchmarkDatasetSpec
    ) -> Tuple[IndexBatch, BenchmarkResult]:
        """Execute full benchmark over dataset fixture recording latency, memory, and throughput."""
        collector = PerformanceCollector()

        # Wire Sync & Index Services
        from ria.application.sync import RepositorySyncService

        sync_service = RepositorySyncService(
            git_client=self._container.git_client,
            registry=self._container.repository_registry,
            lock_manager=self._container.repository_lock,
            workspace_manager=self._container.workspace_manager,
            clock=self._container.clock,
            logger=self._container.logger,
            metrics=self._container.metrics,
        )
        reg_uc = RegisterRepositoryUseCase(sync_service)
        sync_uc = SynchronizeRepositoryUseCase(sync_service)

        # 1. Registration
        with collector.measure_stage("1. Registration", items_processed=1):
            status_dto = reg_uc.execute(
                RegisterRepositoryCommand(
                    remote_url=str(dataset.target_dir), name=dataset.name
                )
            )

        # 2. Clone / Synchronize
        with collector.measure_stage(
            "2. Sync / Clone", items_processed=dataset.file_count
        ):
            # Executed for the clone side effect; the harness only times this stage.
            sync_uc.execute(SynchronizeRepositoryCommand(repo_id=status_dto.repo_id))

        # 3. Setup Index Core
        discovery = FileDiscovery(
            filesystem=self._container.filesystem,
            max_file_size_bytes=self._settings.max_file_size_bytes,
        )
        lang_detect = LanguageDetection(filesystem=self._container.filesystem)
        scanner = RepositoryScanner(
            discovery, lang_detect, self._container.filesystem, self._container.hashing
        )

        plugin_registry = PluginRegistry()
        loader = PluginLoader(plugin_registry)
        loader.load_plugin_class(PythonTreeSitterPlugin)
        loader.load_plugin_class(TypeScriptTreeSitterPlugin)
        loader.load_plugin_class(JavaScriptTreeSitterPlugin)

        builder = IndexUnitBuilder()
        assembler = IndexBatchAssembler()

        pipeline = IndexPipeline(
            scanner=scanner,
            parser_registry=plugin_registry,
            unit_builder=builder,
            batch_assembler=assembler,
            registry=self._container.repository_registry,
            workspace_manager=self._container.workspace_manager,
            filesystem=self._container.filesystem,
            clock=self._container.clock,
            logger=self._container.logger,
            metrics=self._container.metrics,
        )

        # 4. Pipeline Execution (Scan, Discovery, Parse, Unit Build, Assemble)
        with collector.measure_stage(
            "3. Index Pipeline (Scan + Parse + Assemble)",
            items_processed=dataset.file_count,
        ):
            index_batch, pipe_dto = pipeline.execute(
                ExecutePipelineCommand(repo_id=status_dto.repo_id)
            )

        total_elapsed = sum(m.elapsed_seconds for m in collector.stage_metrics)
        peak_memory = max(
            (m.peak_memory_bytes for m in collector.stage_metrics), default=0
        )

        result = BenchmarkResult(
            repo_name=dataset.name,
            language=dataset.language,
            file_count=dataset.file_count,
            repo_size_bytes=dataset.total_bytes,
            commit_sha=dataset.commit_sha,
            branch=dataset.branch,
            total_elapsed_seconds=total_elapsed,
            peak_memory_bytes=peak_memory,
            stage_metrics=collector.stage_metrics,
        )

        return index_batch, result
