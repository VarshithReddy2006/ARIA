"""Comprehensive Concurrency & Repository Isolation Test Suite for Phase 1."""

import multiprocessing
import os
import shutil
import tempfile
import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.api import app
from core.concurrency import repository_lock
from infrastructure.job_executor import LocalJobExecutor
from services.github_service import GitHubService, GitOperationError


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Lock Mutex & Distinct Locks
# ---------------------------------------------------------------------------
def test_same_target_concurrent_locks_serialize():
    """Verify that concurrent locks for the same target serialize execution."""
    repo = "test-owner/repo-lock-test"
    branch = "main"
    execution_order = []

    def task1():
        with repository_lock(repo, branch=branch):
            execution_order.append("task1_start")
            time.sleep(0.08)
            execution_order.append("task1_end")

    def task2():
        time.sleep(0.02)
        with repository_lock(repo, branch=branch):
            execution_order.append("task2_start")
            execution_order.append("task2_end")

    t1 = threading.Thread(target=task1)
    t2 = threading.Thread(target=task2)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert execution_order == ["task1_start", "task1_end", "task2_start", "task2_end"]


def test_different_repositories_execute_concurrently():
    """Verify that different repositories can acquire locks and execute simultaneously."""
    repo_a = "test-owner/repo-a"
    repo_b = "test-owner/repo-b"
    started = []

    def worker_a():
        with repository_lock(repo_a, branch="main"):
            started.append("a")
            time.sleep(0.08)

    def worker_b():
        with repository_lock(repo_b, branch="main"):
            started.append("b")
            time.sleep(0.08)

    t_a = threading.Thread(target=worker_a)
    t_b = threading.Thread(target=worker_b)
    t_a.start()
    t_b.start()
    time.sleep(0.03)

    assert "a" in started and "b" in started
    t_a.join()
    t_b.join()


def test_same_repo_different_branches_execute_concurrently():
    """Verify that main and dev branches of the same repo use independent locks."""
    repo = "test-owner/aria-multi-branch"
    started = []

    def worker_main():
        with repository_lock(repo, branch="main"):
            started.append("main")
            time.sleep(0.08)

    def worker_dev():
        with repository_lock(repo, branch="dev"):
            started.append("dev")
            time.sleep(0.08)

    t_main = threading.Thread(target=worker_main)
    t_dev = threading.Thread(target=worker_dev)
    t_main.start()
    t_dev.start()
    time.sleep(0.03)

    assert "main" in started and "dev" in started
    t_main.join()
    t_dev.join()


# ---------------------------------------------------------------------------
# 2. Branch-Safe Working Tree Paths
# ---------------------------------------------------------------------------
def test_branch_safe_checkout_paths_are_isolated():
    """Verify that different branches resolve to completely independent working-tree directories."""
    gh = GitHubService()
    path_main = gh.get_local_repo_path("VarshithReddy2006/ARIA", branch="main")
    path_dev = gh.get_local_repo_path("VarshithReddy2006/ARIA", branch="dev")
    path_pr = gh.get_local_repo_path(
        "VarshithReddy2006/ARIA", branch="refs/pull/42/head"
    )

    assert path_main != path_dev
    assert path_main != path_pr
    assert path_dev != path_pr
    assert "main" in path_main
    assert "dev" in path_dev
    assert "refs_pull_42_head" in path_pr


# ---------------------------------------------------------------------------
# 3. Cross-Process Locking
# ---------------------------------------------------------------------------
def _child_process_lock_task(repo: str, branch: str, flag_file: str, delay: float):
    with repository_lock(repo, branch=branch):
        with open(flag_file, "a") as f:
            f.write(f"acquired_{branch}\n")
        time.sleep(delay)
        with open(flag_file, "a") as f:
            f.write(f"released_{branch}\n")


def test_cross_process_locking():
    """Verify cross-process mutual exclusion using true multiprocessing."""
    temp_dir = tempfile.mkdtemp()
    flag_file = os.path.join(temp_dir, "lock_events.txt")
    repo = "test-owner/cross-process-repo"

    try:
        p1 = multiprocessing.Process(
            target=_child_process_lock_task, args=(repo, "main", flag_file, 0.1)
        )
        p2 = multiprocessing.Process(
            target=_child_process_lock_task, args=(repo, "main", flag_file, 0.02)
        )

        p1.start()
        time.sleep(0.03)  # Ensure p1 starts first
        p2.start()

        p1.join(timeout=5.0)
        p2.join(timeout=5.0)

        with open(flag_file, "r") as f:
            events = [line.strip() for line in f if line.strip()]

        assert events == [
            "acquired_main",
            "released_main",
            "acquired_main",
            "released_main",
        ]
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 4. Duplicate Job Deduplication
# ---------------------------------------------------------------------------
def test_duplicate_analysis_jobs_are_reused(client):
    """Verify identical concurrent / sequential requests reuse the active job without duplicate workers."""
    import uuid

    mock_executor = MagicMock()
    mock_executor.spawn_analysis.return_value = True
    unique_repo = f"https://github.com/test-owner/test-dedup-{uuid.uuid4().hex[:8]}"

    with patch(
        "infrastructure.job_executor.get_job_executor", return_value=mock_executor
    ):
        payload = {
            "url": unique_repo,
            "branch": "main",
            "force_rebuild": False,
        }

        # Request 1
        resp1 = client.post("/api/v1/analyze", json=payload)
        assert resp1.status_code == 202
        data1 = resp1.json()
        job_id_1 = data1["job_id"]

        # Request 2 (identical target)
        resp2 = client.post("/api/v1/analyze", json=payload)
        assert resp2.status_code == 202
        data2 = resp2.json()
        job_id_2 = data2["job_id"]

        # Proves deduplication reused the active job ID
        assert job_id_1 == job_id_2
        assert mock_executor.spawn_analysis.call_count == 1


def test_different_branches_are_not_deduplicated(client):
    """Verify different branches of the same repository trigger distinct analysis jobs."""
    import uuid

    mock_executor = MagicMock()
    mock_executor.spawn_analysis.return_value = True
    unique_repo = f"https://github.com/test-owner/test-branches-{uuid.uuid4().hex[:8]}"

    with patch(
        "infrastructure.job_executor.get_job_executor", return_value=mock_executor
    ):
        resp_main = client.post(
            "/api/v1/analyze",
            json={"url": unique_repo, "branch": "main"},
        )
        resp_dev = client.post(
            "/api/v1/analyze",
            json={"url": unique_repo, "branch": "dev"},
        )

        assert resp_main.status_code == 202
        assert resp_dev.status_code == 202
        assert resp_main.json()["job_id"] != resp_dev.json()["job_id"]
        assert mock_executor.spawn_analysis.call_count == 2


# ---------------------------------------------------------------------------
# 5. Bounded Local Executor & Backpressure
# ---------------------------------------------------------------------------
def test_bounded_local_executor_respects_max_workers():
    """Verify LocalJobExecutor limits concurrency to configured max_workers."""
    executor = LocalJobExecutor(max_workers=2)
    LocalJobExecutor.reset_pool()

    max_observed_active = 0
    lock = threading.Lock()

    def mock_analysis(repo_url, branch, **kwargs):
        nonlocal max_observed_active
        with lock:
            current = LocalJobExecutor.active_job_count()
            if current > max_observed_active:
                max_observed_active = current
        time.sleep(0.05)
        return {"status": "completed"}

    with patch(
        "backend.routers.repositories.execute_repository_analysis",
        side_effect=mock_analysis,
    ):
        # Spawn 8 jobs
        for i in range(8):
            executor.spawn_analysis(
                job_id=f"test-bounded-{i}",
                repo_url=f"https://github.com/owner/repo-{i}",
                branch="main",
            )

        # Wait for all jobs to complete
        time.sleep(0.6)

        assert max_observed_active <= 2
        assert LocalJobExecutor.active_job_count() == 0
    LocalJobExecutor.reset_pool()


# ---------------------------------------------------------------------------
# 6. Checkout Validation
# ---------------------------------------------------------------------------
def test_checkout_validation_detects_corrupted_directory():
    """Verify _validate_checkout fails fast with GitOperationError on missing/corrupt .git."""
    gh = GitHubService()
    temp_dir = tempfile.mkdtemp()
    try:
        with pytest.raises(GitOperationError) as exc_info:
            gh._validate_checkout(temp_dir, "test-owner/test-repo")
        assert "not a valid git repository" in str(exc_info.value)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
