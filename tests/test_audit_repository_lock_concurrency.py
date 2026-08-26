"""Regression test suite for Phase 2: Concurrency / Repository Lock Serialization."""

import time
import threading
from core.concurrency import repository_lock, get_repository_lock


def test_repository_lock_distinct_locks_per_repo():
    """Verify distinct locks are maintained per canonical repository name."""
    lock_a = get_repository_lock("org/repo-a")
    lock_b = get_repository_lock("org/repo-b")
    assert lock_a is not lock_b

    lock_a_same = get_repository_lock("https://github.com/org/repo-a.git")
    assert lock_a is lock_a_same


def test_repository_lock_mutual_exclusion():
    """Verify that concurrent attempts to acquire lock for same repo block until release."""
    repo = "test-owner/test-concurrency"
    execution_order = []

    def task1():
        with repository_lock(repo):
            execution_order.append("task1_start")
            time.sleep(0.1)
            execution_order.append("task1_end")

    def task2():
        time.sleep(0.02)  # Ensure task1 acquires first
        with repository_lock(repo):
            execution_order.append("task2_start")
            execution_order.append("task2_end")

    t1 = threading.Thread(target=task1)
    t2 = threading.Thread(target=task2)

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert execution_order == ["task1_start", "task1_end", "task2_start", "task2_end"]


def test_concurrent_different_repos_execute_in_parallel():
    """Verify that different repositories can acquire locks and execute simultaneously."""
    repo_a = "test-owner/repo-a"
    repo_b = "test-owner/repo-b"
    started = []

    def worker_a():
        with repository_lock(repo_a):
            started.append("a")
            time.sleep(0.08)

    def worker_b():
        with repository_lock(repo_b):
            started.append("b")
            time.sleep(0.08)

    t_a = threading.Thread(target=worker_a)
    t_b = threading.Thread(target=worker_b)

    t_a.start()
    t_b.start()
    time.sleep(0.03)

    # Both should be inside their respective locks at the same time
    assert "a" in started and "b" in started
    t_a.join()
    t_b.join()
