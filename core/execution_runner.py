"""Parallel execution runner for executing BuildTasks concurrently in stages (PH2-022)."""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from typing import Any, Dict, Generator, List, Optional

from core.analysis_registry import AnalysisRegistry, AnalysisNode
from core.incremental_build_planner import BuildTask
from models.build_event import (
    BuildEvent,
    TaskQueued,
    TaskStarted,
    TaskCompleted,
    TaskSkipped,
    TaskFailed,
    StageCompleted,
    CacheHitEvent,
    LoadEvent,
    CacheMissEvent,
    ProgressEvent,
    SaveEvent,
    BuildTimeEvent,
    ErrorEvent,
)

logger = logging.getLogger(__name__)


def execute_single_task(
    task: BuildTask,
    node: AnalysisNode,
    repo_name: str,
    repo_path: Optional[str],
    files: Optional[List[Dict[str, str]]],
    context: Any,
    force_rebuild: bool,
    build_id: str,
    service_resolver: Optional[Any] = None,
    snapshot_store: Optional[Any] = None,
) -> List[BuildEvent]:
    """Execute a single build task and capture all events generated."""
    from core.logging_context import build_id_var, repository_var, analysis_var

    token_build = build_id_var.set(build_id)
    token_repo = repository_var.set(repo_name)
    token_analysis = analysis_var.set(node.name)

    events: List[BuildEvent] = []

    try:
        if task.mode == "SKIP":
            events.append(TaskSkipped(repo_name, node.name))
            events.append(CacheHitEvent(repo_name, node.name))
            events.append(LoadEvent(repo_name, node.name))
            events.append(BuildTimeEvent(repo_name, node.name, 0.0))
            return events

        events.append(TaskStarted(repo_name, node.name))
        events.append(CacheMissEvent(repo_name, node.name))

        start_time = time.time()

        try:
            # Resolve service singleton via resolver or direct instantiation
            service_instance = None
            if service_resolver is not None:
                service_instance = service_resolver(node.service_class)
            elif node.service_class is not None:
                try:
                    service_instance = node.service_class()
                except Exception:
                    service_instance = None

            if service_instance is not None:
                has_new_api = hasattr(service_instance, "build_full")

                if node.name == "Symbol Index":
                    if has_new_api:
                        if task.mode == "FULL":
                            service_instance.build_full(
                                repo_name, repo_path=repo_path, files=files
                            )
                        else:
                            service_instance.build_partial(
                                repo_name,
                                task.changed_files,
                                repo_path=repo_path,
                                files=files,
                            )
                    else:
                        service_instance.build(
                            repo_name, repo_path=repo_path, files=files
                        )

                elif node.name == "Dependency Graph":
                    if has_new_api:
                        if task.mode == "FULL":
                            service_instance.build_full(
                                repo_name, repo_path=repo_path, files=files
                            )
                        else:
                            service_instance.build_partial(
                                repo_name,
                                task.changed_files,
                                repo_path=repo_path,
                                files=files,
                            )
                    else:
                        service_instance.build(
                            repo_name,
                            repo_path=repo_path,
                            files=files,
                            force_rebuild=force_rebuild,
                        )

                elif node.name == "Call Graph":
                    if has_new_api:
                        if task.mode == "FULL":
                            gen = service_instance.build_full(
                                repo_name, context=context, files=files
                            )
                        else:
                            gen = service_instance.build_partial(
                                repo_name,
                                task.changed_files,
                                context=context,
                                files=files,
                            )
                        for progress in gen:
                            events.append(
                                ProgressEvent(
                                    repo_name, node.name, progress.get("message", "")
                                )
                            )
                    else:
                        service_instance.build(repo_name, context=context)

                elif node.name == "Git History":
                    if has_new_api:
                        if task.mode == "FULL":
                            gen = service_instance.build_full(
                                repo_name, since_days=30, context=context
                            )
                        else:
                            gen = service_instance.build_partial(
                                repo_name,
                                task.changed_files,
                                since_days=30,
                                context=context,
                            )
                    else:
                        gen = service_instance.build(repo_name, since_days=30)
                    for progress in gen:
                        events.append(
                            ProgressEvent(
                                repo_name, node.name, progress.get("message", "")
                            )
                        )

                elif node.name == "API Surface":
                    if has_new_api:
                        if task.mode == "FULL":
                            gen = service_instance.build_full(
                                repo_name, context=context, files=files
                            )
                        else:
                            gen = service_instance.build_partial(
                                repo_name,
                                task.changed_files,
                                context=context,
                                files=files,
                            )
                        for progress in gen:
                            pass
                    else:
                        service_instance.build(repo_name, context=context)
                else:
                    # Custom/mock service execution fallback
                    if has_new_api:
                        if task.mode == "FULL":
                            service_instance.build_full(
                                repo_name, repo_path=repo_path, files=files
                            )
                        else:
                            service_instance.build_partial(
                                repo_name,
                                task.changed_files,
                                repo_path=repo_path,
                                files=files,
                            )
                    elif hasattr(service_instance, "build"):
                        service_instance.build(
                            repo_name, repo_path=repo_path, files=files
                        )
            else:
                # Placeholder for future analyses (service_instance is None)
                if snapshot_store is not None:
                    store = snapshot_store
                else:
                    from storage.snapshot_store import JsonSnapshotStore

                    store = JsonSnapshotStore()

                key = node.outputs[0] if node.outputs else node.name.lower()
                store.save(
                    repo_name,
                    key,
                    {"status": "placeholder", "_schema_version": node.schema_version},
                )

            events.append(SaveEvent(repo_name, node.name))
            duration = (time.time() - start_time) * 1000
            events.append(TaskCompleted(repo_name, node.name, duration))
            events.append(BuildTimeEvent(repo_name, node.name, duration))

            from core.metrics import metrics_registry

            metrics_registry.record_task_duration(
                repo_name, node.name, duration / 1000.0
            )

        except Exception as exc:
            duration = (time.time() - start_time) * 1000
            events.append(TaskFailed(repo_name, node.name, str(exc)))
            events.append(ErrorEvent(repo_name, str(exc), node=node.name))

            from core.metrics import metrics_registry

            metrics_registry.record_task_duration(
                repo_name, node.name, duration / 1000.0
            )
            raise
    finally:
        build_id_var.reset(token_build)
        repository_var.reset(token_repo)
        analysis_var.reset(token_analysis)

    return events


class ParallelExecutionRunner:
    """Orchestrates stage-based parallel build execution using ThreadPoolExecutor."""

    def __init__(
        self,
        repo_name: str,
        repo_path: Optional[str],
        files: Optional[List[Dict[str, str]]],
        context: Any,
        registry: AnalysisRegistry,
        max_workers: Optional[int] = None,
        force_rebuild: bool = False,
        build_id: Optional[str] = None,
        service_resolver: Optional[Any] = None,
        snapshot_store: Optional[Any] = None,
    ) -> None:
        import uuid

        self.repo_name = repo_name
        self.repo_path = repo_path
        self.files = files
        self.context = context
        self.registry = registry
        self.force_rebuild = force_rebuild
        self.build_id = build_id or str(uuid.uuid4())
        self.service_resolver = service_resolver
        self.snapshot_store = snapshot_store

        # Default workers count: max(1, CPU cores - 1)
        if max_workers is None:
            max_workers = max(1, (os.cpu_count() or 4) - 1)
        self.max_workers = max_workers

    def run_stages(
        self, stages: List[List[BuildTask]]
    ) -> Generator[BuildEvent, None, None]:
        """Runs the planned stages sequentially, executing tasks within each stage in parallel."""
        # Yield queued events for all tasks first
        for stage in stages:
            for task in stage:
                yield TaskQueued(self.repo_name, task.analysis)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            for stage_idx, stage in enumerate(stages):
                tasks_in_stage = [task.analysis for task in stage]
                logger.info(
                    "Running stage %d containing tasks: %s",
                    stage_idx,
                    tasks_in_stage,
                )

                # Map task name to AnalysisNode
                node_map = {node.name: node for node in self.registry.get_build_order()}

                futures: Dict[Future[List[BuildEvent]], BuildTask] = {}
                for task in stage:
                    node = node_map.get(task.analysis)
                    if node is None:
                        continue
                    future = executor.submit(
                        execute_single_task,
                        task,
                        node,
                        self.repo_name,
                        self.repo_path,
                        self.files,
                        self.context,
                        self.force_rebuild,
                        self.build_id,
                        self.service_resolver,
                        self.snapshot_store,
                    )
                    futures[future] = task

                # Monitor futures as they complete
                failed = False
                exception_to_raise = None
                completed_task_events: Dict[str, List[BuildEvent]] = {}

                try:
                    for future in as_completed(futures):
                        task = futures[future]
                        try:
                            # future.result() propagates exceptions raised by workers
                            task_events = future.result()
                            completed_task_events[task.analysis] = task_events
                        except Exception as exc:
                            failed = True
                            exception_to_raise = exc
                            logger.error(
                                "Task %s failed: %s. Cancelling remaining tasks in stage %d.",
                                task.analysis,
                                exc,
                                stage_idx,
                            )
                            # Cancel all other pending futures in this stage
                            for pending_future in futures:
                                if pending_future != future:
                                    pending_future.cancel()
                            break
                except Exception as exc:
                    failed = True
                    exception_to_raise = exc

                if failed:
                    if exception_to_raise:
                        raise exception_to_raise
                    else:
                        raise RuntimeError(
                            f"Stage {stage_idx} failed due to worker error."
                        )

                # Stage completed successfully: yield events alphabetically
                stage_tasks_sorted = sorted(stage, key=lambda t: t.analysis)
                for task in stage_tasks_sorted:
                    task_events = completed_task_events.get(task.analysis, [])
                    for event in task_events:
                        yield event

                # Yield StageCompleted event
                yield StageCompleted(self.repo_name, stage_idx, tasks_in_stage)
