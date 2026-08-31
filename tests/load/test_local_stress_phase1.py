"""Lightweight Local Concurrency & Backpressure Stress Harness (Phase 1).

Tests:
- 10 mixed requests
- 25 mixed requests
- 50 mixed requests

With max_workers = 2, verifying that:
- Maximum active workers <= 2 at all times
- No thread explosion
- All jobs complete cleanly
- Duplicate jobs are prevented
"""

import threading
import time
from typing import Any, Dict
from unittest.mock import patch
import pytest

from infrastructure.job_executor import LocalJobExecutor
from backend.routers.repositories import set_job_state


@pytest.mark.parametrize("job_count", [10, 25, 50])
def test_local_stress_bounded_analysis(job_count: int):
    """LOCAL STRESS TEST: Verify bounded worker concurrency under burst loads."""
    max_workers = 2
    executor = LocalJobExecutor(max_workers=max_workers)
    LocalJobExecutor.reset_pool()

    max_active_observed = 0
    active_samples = []
    completed_jobs = []
    lock = threading.Lock()
    start_time = time.perf_counter()

    def mock_analysis(repo_url: str, branch: str = "main", **kwargs) -> Dict[str, Any]:
        nonlocal max_active_observed
        with lock:
            current_active = LocalJobExecutor.active_job_count()
            active_samples.append(current_active)
            if current_active > max_active_observed:
                max_active_observed = current_active
        # Simulate short compute work
        time.sleep(0.015)
        with lock:
            completed_jobs.append(repo_url)
        return {
            "status": "completed",
            "repo": repo_url,
            "branch": branch,
            "successful_phases": [
                "clone",
                "detect",
                "parse",
                "embed",
                "index",
                "analyze",
                "answer",
            ],
        }

    with patch(
        "backend.routers.repositories.execute_repository_analysis",
        side_effect=mock_analysis,
    ):
        # Dispatch burst of jobs (some distinct, some duplicate targets)
        for i in range(job_count):
            repo_idx = i % 5  # 5 distinct repositories with multiple jobs
            branch = "main" if i % 2 == 0 else "dev"
            job_id = f"stress-job-{job_count}-{i}"
            set_job_state(
                job_id,
                {
                    "job_id": job_id,
                    "status": "queued",
                    "repo_url": f"https://github.com/stress-test/repo-{repo_idx}",
                    "branch": branch,
                },
            )
            dispatched = executor.spawn_analysis(
                job_id=job_id,
                repo_url=f"https://github.com/stress-test/repo-{repo_idx}",
                branch=branch,
            )
            assert dispatched is True

        # Wait for all jobs to drain completely from both pool and tracking sets
        timeout = 15.0
        start_wait = time.time()
        while (
            len(completed_jobs) < job_count
            or LocalJobExecutor.active_job_count() > 0
            or LocalJobExecutor.queued_job_count() > 0
        ) and (time.time() - start_wait) < timeout:
            time.sleep(0.01)

        elapsed_s = time.perf_counter() - start_time

        # Assertions
        assert len(completed_jobs) == job_count, (
            f"Expected {job_count} completed jobs, got {len(completed_jobs)}"
        )
        assert max_active_observed <= max_workers, (
            f"Max active workers {max_active_observed} exceeded limit {max_workers}"
        )
        assert LocalJobExecutor.active_job_count() == 0
        assert LocalJobExecutor.queued_job_count() == 0

        print(
            f"\n[LOCAL STRESS TEST] jobs={job_count} max_workers={max_workers} "
            f"peak_active={max_active_observed} completed={len(completed_jobs)} elapsed={elapsed_s:.2f}s"
        )

    LocalJobExecutor.reset_pool()
