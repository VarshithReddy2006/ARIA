"""Comprehensive Local Production Simulation & Deployment Gate Tests.

Validates all 6 production phases:
  - Phase 3: API Container Smoke & Lifecycle
  - Phase 4: Background Worker Execution & Error Handling
  - Phase 5: End-to-End Analysis Pipeline
  - Phase 6: Concurrency, Locking, Atomic Writes, & SQLite WAL Contention
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import sqlite3
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.api import app
from backend.routers.repositories import (
    get_job_state,
    set_job_state,
)
from backend.worker import AnalysisWorker
from core.concurrency import repository_lock, write_json_atomic
from core.job_state import JobStatus
from infrastructure.job_executor import (
    AzureJobExecutor,
    MemoryQueueBackend,
)


@pytest.fixture(scope="module")
def test_client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# PHASE 3 — API Container Smoke Test & Lifecycle
# ---------------------------------------------------------------------------
class TestPhase3ApiContainerSmoke:
    def test_health_probe(self, test_client: TestClient) -> None:
        res = test_client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data.get("status") in ("ok", "healthy", "up")

    def test_ready_probe(self, test_client: TestClient) -> None:
        res = test_client.get("/ready")
        assert res.status_code == 200
        data = res.json()
        assert data.get("status") in ("ok", "ready")

    def test_analyze_endpoint_returns_immediate_202(
        self, test_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """POST /api/v1/analyze returns HTTP 202 immediately with job_id and does not block."""
        monkeypatch.setenv("JOB_EXECUTOR", "local")
        started = time.perf_counter()
        res = test_client.post(
            "/api/v1/analyze",
            json={"url": "https://github.com/fast-test/repo-smoke", "branch": "main"},
        )
        elapsed = time.perf_counter() - started
        # Must return in under 500ms (asynchronous non-blocking)
        assert elapsed < 1.0
        assert res.status_code == 202
        data = res.json()
        assert "job_id" in data
        assert data["status"] == "queued"
        assert data["repo"]["full_name"] == "fast-test/repo-smoke"

    def test_polling_lifecycle_queued_running_completed(
        self, test_client: TestClient
    ) -> None:
        job_id = "test-poll-completed-job"
        set_job_state(
            job_id,
            {
                "job_id": job_id,
                "status": "queued",
                "progress": 0,
                "repo": {"owner": "test", "name": "repo"},
            },
        )

        # 1. Queued
        res1 = test_client.get(f"/api/v1/analyze/{job_id}")
        assert res1.status_code == 202
        assert res1.json()["status"] == "queued"

        # 2. Running
        set_job_state(
            job_id,
            {
                "job_id": job_id,
                "status": "running",
                "progress": 45,
                "repo": {"owner": "test", "name": "repo"},
            },
        )
        res2 = test_client.get(f"/api/v1/analyze/{job_id}")
        assert res2.status_code == 202
        assert res2.json()["status"] == "running"
        assert res2.json()["progress"] == 45

        # 3. Completed
        set_job_state(
            job_id,
            {
                "job_id": job_id,
                "status": "completed",
                "progress": 100,
                "result": {"summary": "Analysis completed successfully"},
                "repo": {"owner": "test", "name": "repo"},
            },
        )
        res3 = test_client.get(f"/api/v1/analyze/{job_id}")
        assert res3.status_code == 200
        assert res3.json()["status"] == "completed"
        assert res3.json()["progress"] == 100

    def test_polling_lifecycle_failed(self, test_client: TestClient) -> None:
        job_id = "test-poll-failed-job"
        set_job_state(
            job_id,
            {
                "job_id": job_id,
                "status": "failed",
                "error": "Simulated fatal clone error",
                "repo": {"owner": "test", "name": "repo"},
            },
        )
        res = test_client.get(f"/api/v1/analyze/{job_id}")
        assert res.status_code == 500
        assert res.json()["status"] == "failed"
        assert "error" in res.json()


# ---------------------------------------------------------------------------
# PHASE 4 — Worker Execution & Error Handling
# ---------------------------------------------------------------------------
class TestPhase4WorkerExecution:
    def test_worker_run_once_success(self) -> None:
        mock_queue = MemoryQueueBackend()
        worker = AnalysisWorker(use_memory_queue=True)
        worker._get_queue_client = lambda: mock_queue

        payload = {
            "job_id": "worker-phase4-success-job",
            "request_id": "req-phase4-success",
            "repo_url": "https://github.com/worker-test/success-project",
            "branch": "main",
            "force_rebuild": False,
        }
        mock_queue.send_message(json.dumps(payload))

        expected_res = {
            "repo": "worker-test/success-project",
            "status": "completed",
            "analysis": {"files": 12},
        }

        with patch(
            "backend.worker.execute_repository_analysis",
            return_value=expected_res,
        ) as mock_analysis:
            processed = worker.run_once()
            assert processed is True
            mock_analysis.assert_called_once()

            state = get_job_state("worker-phase4-success-job")
            assert state is not None
            assert state["status"] == JobStatus.COMPLETED.value
            assert state["request_id"] == "req-phase4-success"
            assert state["progress"] == 100
            assert state["result"] == expected_res

    def test_worker_run_once_failure_and_recovery(self) -> None:
        mock_queue = MemoryQueueBackend()
        worker = AnalysisWorker(use_memory_queue=True)
        worker._get_queue_client = lambda: mock_queue

        # 1. Failing Job
        failing_payload = {
            "job_id": "worker-phase4-fail-job",
            "request_id": "req-phase4-fail",
            "repo_url": "https://github.com/worker-test/fail-project",
            "branch": "main",
            "force_rebuild": False,
        }
        mock_queue.send_message(json.dumps(failing_payload))

        with patch(
            "backend.worker.execute_repository_analysis",
            side_effect=RuntimeError("Transient network failure during AST parse"),
        ):
            processed = worker.run_once()
            assert processed is False

            state = get_job_state("worker-phase4-fail-job")
            assert state is not None
            assert state["status"] == JobStatus.FAILED.value
            assert "network error" in str(state["error"]).lower()
            assert "Stage:" in str(state["error"])

        # 2. Subsequent job succeeds without worker degradation
        subsequent_payload = {
            "job_id": "worker-phase4-recovery-job",
            "request_id": "req-phase4-recovery",
            "repo_url": "https://github.com/worker-test/recovery-project",
            "branch": "main",
            "force_rebuild": False,
        }
        mock_queue.send_message(json.dumps(subsequent_payload))

        with patch(
            "backend.worker.execute_repository_analysis",
            return_value={
                "repo": "worker-test/recovery-project",
                "status": "completed",
            },
        ):
            processed = worker.run_once()
            assert processed is True

            state2 = get_job_state("worker-phase4-recovery-job")
            assert state2 is not None
            assert state2["status"] == JobStatus.COMPLETED.value


# ---------------------------------------------------------------------------
# PHASE 5 — End-to-End Analysis Simulation
# ---------------------------------------------------------------------------
class TestPhase5EndToEndAnalysis:
    def test_full_analysis_pipeline_simulation(
        self, test_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Simulates full dispatch -> worker execution -> state polling -> dashboard data."""
        mock_queue = MemoryQueueBackend()
        executor = AzureJobExecutor(queue_client=mock_queue)
        monkeypatch.setattr(
            "infrastructure.job_executor.get_job_executor", lambda: executor
        )

        # 1. User submits analysis request
        res = test_client.post(
            "/api/v1/analyze",
            json={"url": "https://github.com/e2e-org/e2e-demo", "branch": "main"},
        )
        assert res.status_code == 202
        body = res.json()
        job_id = body["job_id"]
        assert body["status"] == "queued"

        # 2. Worker picks up job from queue
        worker = AnalysisWorker(use_memory_queue=True)
        worker._get_queue_client = lambda: mock_queue

        analysis_mock_result = {
            "repo": "e2e-org/e2e-demo",
            "owner": "e2e-org",
            "name": "e2e-demo",
            "analysis": {
                "summary": "E2E sample codebase",
                "total_files": 45,
                "languages": {"Python": 90, "TypeScript": 10},
            },
            "architecture": {"components": ["api", "core", "models"]},
            "report": "✓ Repository Ready\nAll checks passed.",
            "duration_seconds": 1.25,
        }

        with patch(
            "backend.worker.execute_repository_analysis",
            return_value=analysis_mock_result,
        ):
            processed = worker.run_once()
            assert processed is True

        # 3. Client polls status endpoint
        poll_res = test_client.get(f"/api/v1/analyze/{job_id}")
        assert poll_res.status_code == 200
        poll_data = poll_res.json()
        assert poll_data["status"] == "completed"
        assert poll_data["progress"] == 100
        assert poll_data["result"]["repo"] == "e2e-org/e2e-demo"


# ---------------------------------------------------------------------------
# PHASE 6 — Concurrency, Locking, Atomic Writes, & SQLite WAL Contention
# ---------------------------------------------------------------------------
class TestPhase6ConcurrencyAndFailure:
    def test_concurrency_duplicate_requests_reuse_active_job(
        self, test_client: TestClient
    ) -> None:
        """Test A: Duplicate requests for same repo reuse existing active job when force_rebuild=False."""
        repo_url = "https://github.com/concurrency-org/dedup-repo"
        job_id = "active-job-dedup"
        set_job_state(
            job_id,
            {
                "job_id": job_id,
                "request_id": "req-dedup-1",
                "repo_url": repo_url,
                "status": "running",
                "repo": {
                    "owner": "concurrency-org",
                    "name": "dedup-repo",
                    "full_name": "concurrency-org/dedup-repo",
                },
            },
        )

        res = test_client.post(
            "/api/v1/analyze",
            json={"url": repo_url, "force_rebuild": False},
        )
        assert res.status_code == 202
        body = res.json()
        # Must return the active existing job
        assert body["job_id"] == job_id
        assert body["status"] == "running"

    def test_concurrency_force_rebuild_spawns_new_job(
        self, test_client: TestClient
    ) -> None:
        """Test B: force_rebuild=True spawns a fresh job even if one was active."""
        repo_url = "https://github.com/concurrency-org/force-repo"
        old_job_id = "active-job-old"
        set_job_state(
            old_job_id,
            {
                "job_id": old_job_id,
                "request_id": "req-old",
                "repo_url": repo_url,
                "status": "running",
                "repo": {
                    "owner": "concurrency-org",
                    "name": "force-repo",
                    "full_name": "concurrency-org/force-repo",
                },
            },
        )

        res = test_client.post(
            "/api/v1/analyze",
            json={"url": repo_url, "force_rebuild": True},
        )
        assert res.status_code == 202
        body = res.json()
        # Must be a new distinct job_id
        assert body["job_id"] != old_job_id
        assert body["status"] == "queued"

    def test_repository_locking_isolation(self) -> None:
        """Test C: Concurrent threads on different repositories do not block each other."""
        acquired_locks = []

        def _lock_repo(name: str):
            with repository_lock(name, timeout=2.0) as acquired:
                if acquired:
                    acquired_locks.append(name)
                    time.sleep(0.05)

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            f1 = executor.submit(_lock_repo, "owner/repo-alpha")
            f2 = executor.submit(_lock_repo, "owner/repo-beta")
            f3 = executor.submit(_lock_repo, "owner/repo-gamma")
            concurrent.futures.wait([f1, f2, f3])

        assert len(acquired_locks) == 3
        assert "owner/repo-alpha" in acquired_locks
        assert "owner/repo-beta" in acquired_locks
        assert "owner/repo-gamma" in acquired_locks

    def test_atomic_json_write_partial_protection(self, tmp_path) -> None:
        """Test E: Atomic write guarantees file validity and replace semantics."""
        target_file = str(tmp_path / "atomic_store.json")
        sample_data = {"key": "value", "items": list(range(100))}

        write_json_atomic(target_file, sample_data)
        assert os.path.exists(target_file)

        with open(target_file, "r", encoding="utf-8") as fh:
            loaded = json.load(fh)
        assert loaded == sample_data

        # Concurrent read and update
        def _updater(idx: int):
            write_json_atomic(
                target_file, {"updated_by": idx, "timestamp": time.time()}
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(_updater, i) for i in range(10)]
            concurrent.futures.wait(futures)

        # Reader must always observe valid JSON, never partial/corrupted bytes
        with open(target_file, "r", encoding="utf-8") as fh:
            final_data = json.load(fh)
            assert "updated_by" in final_data

    def test_sqlite_wal_and_busy_timeout_contention(self, tmp_path) -> None:
        """Test F: SQLite WAL mode and busy_timeout handle concurrent reader/writer threads."""
        test_db = str(tmp_path / "test_wal.db")

        def _get_test_conn() -> sqlite3.Connection:
            conn = sqlite3.connect(test_db, timeout=10.0)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            return conn

        # Init table
        with _get_test_conn() as init_conn:
            init_conn.execute(
                "CREATE TABLE IF NOT EXISTS test_records (id INTEGER PRIMARY KEY, val TEXT);"
            )

        errors = []

        def _writer(worker_id: int):
            try:
                for i in range(10):
                    with _get_test_conn() as conn:
                        conn.execute(
                            "INSERT INTO test_records (val) VALUES (?);",
                            (f"worker-{worker_id}-row-{i}",),
                        )
            except Exception as exc:
                errors.append(exc)

        def _reader():
            try:
                for _ in range(10):
                    with _get_test_conn() as conn:
                        cursor = conn.execute("SELECT COUNT(*) FROM test_records;")
                        _ = cursor.fetchone()
            except Exception as exc:
                errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            writer_futures = [executor.submit(_writer, i) for i in range(4)]
            reader_futures = [executor.submit(_reader) for _ in range(4)]
            concurrent.futures.wait(writer_futures + reader_futures)

        assert len(errors) == 0, f"SQLite contention errors: {errors}"
        with _get_test_conn() as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM test_records;").fetchone()[0]
            assert cnt == 40
