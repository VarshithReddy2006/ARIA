"""Focused regression tests for Azure async analysis dispatch reliability."""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from backend.api import app
from backend.routers.repositories import get_job_state


@pytest.fixture
def client():
    return TestClient(app)


def test_dispatch_success_returns_202(client):
    """Proves successful executor dispatch returns HTTP 202 with job_id and queued state."""
    mock_executor = MagicMock()
    mock_executor.spawn_analysis.return_value = True

    with patch(
        "infrastructure.job_executor.get_job_executor", return_value=mock_executor
    ):
        payload = {
            "url": "https://github.com/test-owner/test-dispatch-success",
            "branch": "main",
            "force_rebuild": True,
        }
        response = client.post("/api/v1/analyze", json=payload)
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "queued"
        assert data["repo"]["owner"] == "test-owner"
        assert data["repo"]["name"] == "test-dispatch-success"

        job_id = data["job_id"]
        mock_executor.spawn_analysis.assert_called_once()
        call_kwargs = mock_executor.spawn_analysis.call_args.kwargs
        assert call_kwargs["job_id"] == job_id
        assert (
            call_kwargs["repo_url"]
            == "https://github.com/test-owner/test-dispatch-success"
        )

        state = get_job_state(job_id)
        assert state is not None
        assert state["status"] == "queued"


def test_dispatch_returning_false_results_in_503_and_failed_state(client):
    """Proves executor.spawn_analysis() returning False results in HTTP 503 and persisted failed job state."""
    mock_executor = MagicMock()
    mock_executor.spawn_analysis.return_value = False

    with patch(
        "infrastructure.job_executor.get_job_executor", return_value=mock_executor
    ):
        payload = {
            "url": "https://github.com/test-owner/test-dispatch-false",
            "branch": "main",
            "force_rebuild": True,
        }
        response = client.post("/api/v1/analyze", json=payload)
        assert response.status_code == 503
        data = response.json()
        assert data["detail"] == "Analysis worker is currently unavailable."

        mock_executor.spawn_analysis.assert_called_once()
        job_id = mock_executor.spawn_analysis.call_args.kwargs["job_id"]

        state = get_job_state(job_id)
        assert state is not None
        assert state["status"] == "failed"
        assert state["message"] == "Failed to queue analysis job"
        assert state["error"] is not None
        assert "Stage:" in state["error"]


def test_dispatch_exception_results_in_503_and_failed_state(client):
    """Proves executor.spawn_analysis() raising an exception results in HTTP 503 and persisted failed job state."""
    mock_executor = MagicMock()
    mock_executor.spawn_analysis.side_effect = RuntimeError(
        "Azure Storage Queue connection timeout: https://secret-account.queue.core.windows.net?sig=super_secret_sas_token"
    )

    with patch(
        "infrastructure.job_executor.get_job_executor", return_value=mock_executor
    ):
        payload = {
            "url": "https://github.com/test-owner/test-dispatch-error",
            "branch": "main",
            "force_rebuild": True,
        }
        response = client.post("/api/v1/analyze", json=payload)
        assert response.status_code == 503
        data = response.json()
        assert data["detail"] == "Analysis worker is currently unavailable."
        # Verify secret token is NOT leaked in HTTP response
        assert "super_secret_sas_token" not in str(data)
        assert "secret-account" not in str(data)

        mock_executor.spawn_analysis.assert_called_once()
        job_id = mock_executor.spawn_analysis.call_args.kwargs["job_id"]

        state = get_job_state(job_id)
        assert state is not None
        assert state["status"] == "failed"
        assert state["message"] == "Failed to queue analysis job"
        assert state["error"] is not None
        # Verify sanitized error format and no secret leaks
        assert "Stage: Analysis Pipeline" in state["error"]
        assert "super_secret_sas_token" not in state["error"]
        assert "secret-account" not in state["error"]
