"""Unit and integration tests for Azure migration and JobExecutor abstraction."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from core.job_state import JobStatus
from infrastructure.job_executor import (
    AzureJobExecutor,
    LocalJobExecutor,
    MemoryQueueBackend,
    ModalJobExecutor,
    get_job_executor,
    get_shared_local_queue,
)
from backend.worker import AnalysisWorker


# ---------------------------------------------------------------------------
# 1. JobExecutor Factory & Selection
# ---------------------------------------------------------------------------
class TestJobExecutorFactory:
    def test_default_executor_is_local(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("JOB_EXECUTOR", raising=False)
        executor = get_job_executor()
        assert isinstance(executor, LocalJobExecutor)

    def test_select_local_executor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("JOB_EXECUTOR", "local")
        executor = get_job_executor()
        assert isinstance(executor, LocalJobExecutor)

    def test_select_modal_executor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("JOB_EXECUTOR", "modal")
        executor = get_job_executor()
        assert isinstance(executor, ModalJobExecutor)

    def test_select_azure_executor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("JOB_EXECUTOR", "azure")
        executor = get_job_executor()
        assert isinstance(executor, AzureJobExecutor)

    def test_invalid_executor_raises_value_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("JOB_EXECUTOR", "unsupported_cloud")
        with pytest.raises(
            ValueError, match="Unknown JOB_EXECUTOR 'unsupported_cloud'"
        ):
            get_job_executor()


# ---------------------------------------------------------------------------
# 2. AzureJobExecutor & Queue Serialization
# ---------------------------------------------------------------------------
class TestAzureJobExecutor:
    def test_serialize_payload_preserves_ids_and_flags(self) -> None:
        executor = AzureJobExecutor(use_memory_queue=True)
        raw = executor.serialize_payload(
            job_id="job-123",
            repo_url="https://github.com/acme/widget",
            branch="feature-x",
            force_rebuild=True,
            request_id="req-999",
        )
        data = json.loads(raw)
        assert data["job_id"] == "job-123"
        assert data["request_id"] == "req-999"
        assert data["repo_url"] == "https://github.com/acme/widget"
        assert data["branch"] == "feature-x"
        assert data["force_rebuild"] is True
        assert "enqueued_at" in data

    def test_serialize_payload_defaults_request_id_to_job_id(self) -> None:
        executor = AzureJobExecutor(use_memory_queue=True)
        raw = executor.serialize_payload(
            job_id="job-abc",
            repo_url="https://github.com/acme/widget",
        )
        data = json.loads(raw)
        assert data["request_id"] == "job-abc"
        assert data["branch"] == "main"
        assert data["force_rebuild"] is False

    def test_spawn_analysis_enqueues_to_memory_queue(self) -> None:
        mock_queue = MemoryQueueBackend()
        executor = AzureJobExecutor(queue_client=mock_queue)

        dispatched = executor.spawn_analysis(
            job_id="test-job-42",
            repo_url="https://github.com/test/repo",
            branch="main",
            request_id="req-42",
        )
        assert dispatched is True
        assert mock_queue.qsize() == 1

        msg = mock_queue.receive_message()
        assert msg is not None
        payload = json.loads(msg)
        assert payload["job_id"] == "test-job-42"
        assert payload["request_id"] == "req-42"

    def test_missing_azure_credentials_raises_explicit_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
        monkeypatch.delenv("AZURE_USE_MEMORY_QUEUE", raising=False)
        executor = AzureJobExecutor()
        with pytest.raises(
            RuntimeError, match="AZURE_STORAGE_CONNECTION_STRING is not configured"
        ):
            executor.spawn_analysis("job-1", "https://github.com/test/repo")


# ---------------------------------------------------------------------------
# 3. ModalJobExecutor Regression
# ---------------------------------------------------------------------------
class TestModalJobExecutor:
    def test_modal_spawn_invokes_modal_function(self) -> None:
        mock_spawn = MagicMock()
        mock_modal_app = MagicMock()
        mock_modal_app.run_analysis_job.spawn = mock_spawn

        with patch.dict("sys.modules", {"modal_app": mock_modal_app}):
            executor = ModalJobExecutor()
            dispatched = executor.spawn_analysis(
                job_id="modal-job-1",
                repo_url="https://github.com/modal/test",
                branch="main",
                force_rebuild=False,
                request_id="modal-req-1",
            )
            assert dispatched is True
            mock_spawn.assert_called_once_with(
                repo_url="https://github.com/modal/test",
                branch="main",
                force_rebuild=False,
                request_id="modal-req-1",
                job_id="modal-job-1",
            )


# ---------------------------------------------------------------------------
# 4. AnalysisWorker Execution & State Lifecycle
# ---------------------------------------------------------------------------
class TestAnalysisWorker:
    def test_worker_success_lifecycle(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_queue = MemoryQueueBackend()
        worker = AnalysisWorker(use_memory_queue=True)
        worker._get_queue_client = lambda: mock_queue

        # Enqueue job
        payload = {
            "job_id": "job-worker-success",
            "request_id": "req-worker-success",
            "repo_url": "https://github.com/owner/success-repo",
            "branch": "main",
            "force_rebuild": False,
        }
        mock_queue.send_message(json.dumps(payload))

        fake_analysis_result = {
            "status": "completed",
            "repo": "owner/success-repo",
            "summary": "all good",
        }

        with patch(
            "backend.worker.execute_repository_analysis",
            return_value=fake_analysis_result,
        ) as mock_exec:
            processed = worker.run_once()
            assert processed is True
            mock_exec.assert_called_once()

            from backend.routers.repositories import get_job_state

            state = get_job_state("job-worker-success")
            assert state is not None
            assert state["status"] == JobStatus.COMPLETED.value
            assert state["progress"] == 100
            assert state["result"] == fake_analysis_result
            assert "completed_at" in state

    def test_worker_failure_lifecycle(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_queue = MemoryQueueBackend()
        worker = AnalysisWorker(use_memory_queue=True)
        worker._get_queue_client = lambda: mock_queue

        payload = {
            "job_id": "job-worker-fail",
            "request_id": "req-worker-fail",
            "repo_url": "https://github.com/owner/fail-repo",
            "branch": "main",
            "force_rebuild": False,
        }
        mock_queue.send_message(json.dumps(payload))

        with patch(
            "backend.worker.execute_repository_analysis",
            side_effect=RuntimeError("Simulated pipeline error"),
        ):
            processed = worker.run_once()
            assert processed is False

            from backend.routers.repositories import get_job_state

            state = get_job_state("job-worker-fail")
            assert state is not None
            assert state["status"] == JobStatus.FAILED.value
            assert "error" in state
            assert "completed_at" in state

    def test_worker_empty_queue_returns_false(self) -> None:
        mock_queue = MemoryQueueBackend()
        worker = AnalysisWorker(use_memory_queue=True)
        worker._get_queue_client = lambda: mock_queue
        assert worker.run_once() is False


# ---------------------------------------------------------------------------
# 5. API Dispatch Integration & No Duplicate Active Jobs
# ---------------------------------------------------------------------------
class TestApiJobDispatch:
    def test_api_dispatches_via_configured_executor(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from fastapi.testclient import TestClient
        from backend.api import app

        mock_queue = get_shared_local_queue()
        # Drain any existing messages
        while not mock_queue.empty():
            mock_queue.receive_message()

        monkeypatch.setenv("JOB_EXECUTOR", "azure")
        monkeypatch.setenv("AZURE_USE_MEMORY_QUEUE", "1")

        client = TestClient(app)
        res = client.post(
            "/api/v1/analyze",
            json={"url": "https://github.com/test-org/test-dispatch", "branch": "main"},
        )
        assert res.status_code == 202
        body = res.json()
        assert "job_id" in body
        assert body["status"] == "queued"
        assert mock_queue.qsize() == 1

        msg = mock_queue.receive_message()
        assert msg is not None
        payload = json.loads(msg)
        assert payload["job_id"] == body["job_id"]
        assert payload["repo_url"] == "https://github.com/test-org/test-dispatch"

    def test_api_returns_existing_job_when_active_and_no_force_rebuild(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from fastapi.testclient import TestClient
        from backend.api import app
        from backend.routers.repositories import set_job_state

        client = TestClient(app)
        job_id = "existing-active-job"
        set_job_state(
            job_id,
            {
                "job_id": job_id,
                "request_id": "req-existing",
                "repo_url": "https://github.com/active/project",
                "status": "running",
                "repo": {
                    "owner": "active",
                    "name": "project",
                    "full_name": "active/project",
                },
            },
        )

        res = client.post(
            "/api/v1/analyze",
            json={"url": "https://github.com/active/project", "force_rebuild": False},
        )
        assert res.status_code == 202
        body = res.json()
        assert body["job_id"] == job_id
        assert body["status"] == "running"
