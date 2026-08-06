"""Unit tests for Phase 2.2 Parallel Analysis Execution (PH2-022)."""

import pytest
import time
import tempfile
import shutil
import threading

from core.analysis_registry import AnalysisRegistry
from core.incremental_build_planner import BuildTask
from core.execution_scheduler import ExecutionScheduler
from core.execution_runner import ParallelExecutionRunner
from core.cache import AnalysisCache
from storage.snapshot_store import JsonSnapshotStore


def test_scheduler_stages():
    """Verify that ExecutionScheduler groups tasks into correct topological stages."""
    registry = AnalysisRegistry()
    # A (root)
    # B (depends A)
    # C (depends A)
    # D (depends B, C)
    registry.register("A", type(None), dependencies=[], outputs=["a"])
    registry.register("B", type(None), dependencies=["A"], outputs=["b"])
    registry.register("C", type(None), dependencies=["A"], outputs=["c"])
    registry.register("D", type(None), dependencies=["B", "C"], outputs=["d"])

    tasks = [
        BuildTask("A", "FULL", set(), []),
        BuildTask("B", "FULL", set(), []),
        BuildTask("C", "PARTIAL", set(), []),
        BuildTask("D", "SKIP", set(), []),
    ]

    stages = ExecutionScheduler.schedule(tasks, registry)

    assert len(stages) == 3
    # Stage 0: A
    assert [t.analysis for t in stages[0]] == ["A"]
    # Stage 1: B and C (sorted alphabetically: B first, C second)
    assert [t.analysis for t in stages[1]] == ["B", "C"]
    # Stage 2: D
    assert [t.analysis for t in stages[2]] == ["D"]


def test_runner_concurrency(monkeypatch):
    """Verify that independent tasks are executed concurrently in the runner."""

    class MockServiceA:
        def build_full(self, repo_name, repo_path=None, files=None):
            time.sleep(0.15)  # 150ms sleep

    class MockServiceB:
        def build_full(self, repo_name, repo_path=None, files=None):
            time.sleep(0.15)  # 150ms sleep

    # Mock dependencies resolver
    service_a = MockServiceA()
    service_b = MockServiceB()

    def mock_get_service(cls):
        if cls == MockServiceA:
            return service_a
        if cls == MockServiceB:
            return service_b
        return None

    monkeypatch.setattr("backend.dependencies.get_service_by_class", mock_get_service)

    # Build registry
    registry = AnalysisRegistry()
    registry.register("TaskA", MockServiceA, dependencies=[], outputs=["a"])
    registry.register("TaskB", MockServiceB, dependencies=[], outputs=["b"])

    tasks = [
        BuildTask("TaskA", "FULL", set(), []),
        BuildTask("TaskB", "FULL", set(), []),
    ]

    # Schedule: both TaskA and TaskB have 0 dependencies, so they should be in Stage 0
    stages = ExecutionScheduler.schedule(tasks, registry)
    assert len(stages) == 1
    assert len(stages[0]) == 2

    runner = ParallelExecutionRunner(
        repo_name="test/parallel_repo",
        repo_path=None,
        files=[],
        context=None,
        registry=registry,
        max_workers=2,
    )

    start_time = time.time()
    events = list(runner.run_stages(stages))
    end_time = time.time()
    elapsed = end_time - start_time

    # Sequential duration would be 150ms + 150ms = 300ms.
    # Concurrently it should take ~150ms + scheduling overhead (< 220ms).
    assert elapsed < 0.25, f"Execution took too long: {elapsed:.2f}s (not concurrent)"

    # Check that events were emitted
    event_types = {e.event_type for e in events}
    assert "TASK_STARTED" in event_types
    assert "TASK_COMPLETED" in event_types
    assert "STAGE_COMPLETED" in event_types


def test_runner_exception_handling(monkeypatch):
    """Verify that a task failure propagates and cancels subsequent executions."""

    class MockServiceOk:
        def build_full(self, *args, **kwargs):
            pass

    class MockServiceFail:
        def build_full(self, *args, **kwargs):
            raise ValueError("Intentional Task Failure")

    service_ok = MockServiceOk()
    service_fail = MockServiceFail()

    def mock_get_service(cls):
        if cls == MockServiceOk:
            return service_ok
        if cls == MockServiceFail:
            return service_fail
        return None

    monkeypatch.setattr("backend.dependencies.get_service_by_class", mock_get_service)

    registry = AnalysisRegistry()
    registry.register("TaskOk", MockServiceOk, dependencies=[], outputs=["ok"])
    registry.register("TaskFail", MockServiceFail, dependencies=[], outputs=["fail"])
    # TaskDownstream depends on TaskFail, should not run
    registry.register(
        "TaskDownstream",
        MockServiceOk,
        dependencies=["TaskFail"],
        outputs=["downstream"],
    )

    tasks = [
        BuildTask("TaskOk", "FULL", set(), []),
        BuildTask("TaskFail", "FULL", set(), []),
        BuildTask("TaskDownstream", "FULL", set(), []),
    ]

    stages = ExecutionScheduler.schedule(tasks, registry)
    # Stage 0: TaskOk, TaskFail (parallel)
    # Stage 1: TaskDownstream

    runner = ParallelExecutionRunner(
        repo_name="test/failure_repo",
        repo_path=None,
        files=[],
        context=None,
        registry=registry,
        max_workers=2,
    )

    with pytest.raises(ValueError, match="Intentional Task Failure"):
        list(runner.run_stages(stages))


def test_runner_deterministic_event_ordering(monkeypatch):
    """Verify that events are sorted alphabetically by task name within a stage."""

    class MockServiceA:
        def build_full(self, *args, **kwargs):
            time.sleep(0.08)  # finishes second

    class MockServiceB:
        def build_full(self, *args, **kwargs):
            time.sleep(0.01)  # finishes first

    service_a = MockServiceA()
    service_b = MockServiceB()

    def mock_get_service(cls):
        if cls == MockServiceA:
            return service_a
        if cls == MockServiceB:
            return service_b
        return None

    monkeypatch.setattr("backend.dependencies.get_service_by_class", mock_get_service)

    registry = AnalysisRegistry()
    registry.register("TaskA", MockServiceA, dependencies=[], outputs=["a"])
    registry.register("TaskB", MockServiceB, dependencies=[], outputs=["b"])

    tasks = [
        BuildTask("TaskA", "FULL", set(), []),
        BuildTask("TaskB", "FULL", set(), []),
    ]

    stages = ExecutionScheduler.schedule(tasks, registry)
    runner = ParallelExecutionRunner(
        repo_name="test/ordering_repo",
        repo_path=None,
        files=[],
        context=None,
        registry=registry,
        max_workers=2,
    )

    events = list(runner.run_stages(stages))

    # Filter completed events
    completed_events = [e for e in events if e.event_type == "TASK_COMPLETED"]
    assert len(completed_events) == 2
    # TaskA must precede TaskB in the yielded events list due to alphabetical sorting,
    # even though TaskB finished much earlier.
    assert completed_events[0].node == "TaskA"
    assert completed_events[1].node == "TaskB"


def test_cache_thread_safety():
    """Stress test AnalysisCache under concurrent load from multiple threads."""
    cache = AnalysisCache()
    repo = "test/thread_repo"

    errors = []

    def worker(worker_id: int):
        try:
            for i in range(100):
                key = f"key_{i}"
                cache.set(repo, key, {"val": i, "worker": worker_id}, 1)
                val = cache.get(repo, key, 1)
                assert val is not None
                # Concurrent stats modifications
                cache.get_stats()
                if i % 10 == 0:
                    cache.invalidate(repo, key)
        except Exception as exc:  # noqa: BLE001
            # Intentional: collect any exception raised from worker threads, including
            # the AssertionErrors above, so the test can fail after all threads join.
            # An exception escaping here would be swallowed by threading and the test
            # would pass silently, so narrowing the type is not possible.
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Thread safety errors occurred: {errors}"


def test_snapshot_store_thread_safety():
    """Stress test JsonSnapshotStore under concurrent saves from multiple threads."""
    tmpdir = tempfile.mkdtemp()
    store = JsonSnapshotStore(base_dir=tmpdir)
    repo = "test/thread_repo"

    errors = []

    def worker(worker_id: int):
        try:
            for i in range(50):
                # Write to different keys concurrently
                key = f"key_{worker_id}_{i}"
                payload = {"data": i, "worker": worker_id, "_schema_version": 1}
                store.save(repo, key, payload)
                loaded = store.load(repo, key)
                assert loaded is not None
                assert loaded["data"] == i
        except Exception as exc:  # noqa: BLE001
            # Intentional: collect any exception raised from worker threads, including
            # the AssertionErrors above, so the test can fail after all threads join.
            # An exception escaping here would be swallowed by threading and the test
            # would pass silently, so narrowing the type is not possible.
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    shutil.rmtree(tmpdir)
    assert len(errors) == 0, f"SnapshotStore thread safety errors: {errors}"
