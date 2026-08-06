"""Event-driven build pipeline orchestrating FULL, PARTIAL, and SKIP tasks (PH2-021)."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Generator, List, Optional

from core.analysis_registry import AnalysisRegistry
from core.change_detector import ChangeDetector
from core.incremental_build_planner import IncrementalBuildPlanner
from core.repository_context import RepositoryContext
from models.build_manifest import BuildManifest

logger = logging.getLogger(__name__)


class BuildPipeline:
    """Pipeline orchestrating builder steps based on incremental ChangeSet tasks."""

    def __init__(
        self,
        registry: AnalysisRegistry,
        snapshot_store: Optional[Any] = None,
        graph_service: Optional[Any] = None,
    ) -> None:
        self.registry = registry
        self._snapshot_store = snapshot_store
        self._graph_service = graph_service

    def build(
        self,
        repo_name: str,
        repo_path: Optional[str] = None,
        files: Optional[List[Dict[str, str]]] = None,
        force_rebuild: bool = False,
        max_workers: Optional[int] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """Execute build tasks (FULL, PARTIAL, SKIP) and yield process events."""
        import uuid
        from core.logging_context import build_id_var, repository_var

        build_id = str(uuid.uuid4())
        token_build = build_id_var.set(build_id)
        token_repo = repository_var.set(repo_name)

        start_time = time.time()
        yield {
            "event": "START",
            "repo_name": repo_name,
            "timestamp": start_time,
        }

        try:
            # 1. Resolve file list
            if files is not None:
                file_list = files
            elif repo_path is not None:
                file_list = ChangeDetector.scan_directory(repo_path)
            else:
                file_list = []

            # 2. Ingest snapshot store & graph service dependencies
            if self._snapshot_store is not None:
                snapshot_store = self._snapshot_store
            else:
                from storage.snapshot_store import JsonSnapshotStore

                snapshot_store = JsonSnapshotStore()
                
            graph_service = self._graph_service

            # 3. Load previous manifest
            old_manifest_data = snapshot_store.load(repo_name, "build_manifest")
            old_manifest = None
            if old_manifest_data:
                try:
                    old_manifest = BuildManifest.model_validate(old_manifest_data)
                except Exception as exc:
                    logger.warning("Stale or malformed build manifest ignored: %s", exc)

            # 4. Change detection
            detector = ChangeDetector()
            change_set, file_hashes, repo_hash = detector.detect_changes(
                file_list, old_manifest
            )

            # 5. Generate build plan
            build_tasks = IncrementalBuildPlanner.plan(
                repo_name,
                change_set,
                self.registry,
                old_manifest,
                snapshot_store,
                graph_service,
                force_rebuild=force_rebuild,
            )
        except Exception as exc:
            yield {
                "event": "ERROR",
                "repo_name": repo_name,
                "message": f"Change detection or build planning failed: {exc}",
                "timestamp": time.time(),
            }
            build_id_var.reset(token_build)
            repository_var.reset(token_repo)
            return

        # Single RepositoryContext instance created for the build request lifecycle
        context = RepositoryContext(repo_name, repo_path=repo_path)
        nodes = self.registry.get_build_order()

        from core.execution_scheduler import ExecutionScheduler
        from core.execution_runner import ParallelExecutionRunner
        from models.build_event import BuildCompleted

        try:
            # 1. Schedule tasks into topological stages
            stages = ExecutionScheduler.schedule(build_tasks, self.registry)

            # 2. Instantiate and run ParallelExecutionRunner
            runner = ParallelExecutionRunner(
                repo_name=repo_name,
                repo_path=repo_path,
                files=file_list,
                context=context,
                registry=self.registry,
                max_workers=max_workers,
                force_rebuild=force_rebuild,
                build_id=build_id,
            )

            for event in runner.run_stages(stages):
                yield event.to_dict()

        except Exception as exc:
            logger.error(
                "Build execution failed: %s",
                exc,
                exc_info=True,
            )
            yield {
                "event": "ERROR",
                "repo_name": repo_name,
                "message": str(exc),
                "timestamp": time.time(),
            }
            build_id_var.reset(token_build)
            repository_var.reset(token_repo)
            return

        # 8. All tasks completed successfully! Save BuildManifest.
        try:
            new_manifest = BuildManifest(
                repository_hash=repo_hash,
                file_hashes=file_hashes,
                schema_versions={node.name: node.schema_version for node in nodes},
                snapshot_versions={node.name: node.schema_version for node in nodes},
                last_successful_build=time.time(),
                build_duration_ms=(time.time() - start_time) * 1000,
            )
            snapshot_store.save(repo_name, "build_manifest", new_manifest.model_dump())
        except Exception as exc:
            logger.error("Failed to save BuildManifest: %s", exc)

        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000

        # Record metrics duration
        from core.metrics import metrics_registry

        metrics_registry.record_build_duration(repo_name, (end_time - start_time))

        # Yield BuildCompleted and legacy END events
        yield BuildCompleted(repo_name, duration_ms).to_dict()
        yield {
            "event": "END",
            "repo_name": repo_name,
            "duration_ms": duration_ms,
            "timestamp": end_time,
        }

        # Reset context variables
        build_id_var.reset(token_build)
        repository_var.reset(token_repo)
