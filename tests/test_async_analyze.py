"""Tests for asynchronous repository analysis and polling endpoints."""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from backend.api import app
from backend.routers.repositories import (
    execute_repository_analysis,
    set_job_state,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_post_analyze_returns_immediately_with_job_id(client):
    """POST /api/v1/analyze returns HTTP 202 with job_id immediately."""
    payload = {
        "url": "https://github.com/fastapi/fastapi",
        "branch": "main",
    }
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "queued"
    assert "request_id" in data
    assert data["repo"]["owner"] == "fastapi"
    assert data["repo"]["name"] == "fastapi"


def test_get_analyze_status_unknown_job(client):
    """GET /api/v1/analyze/{job_id} returns 404 for unknown job."""
    response = client.get("/api/v1/analyze/unknown_job_9999")
    assert response.status_code == 404


def test_get_analyze_status_running_and_completed(client):
    """GET /api/v1/analyze/{job_id} returns 202 while running, 200 when completed."""
    job_id = "test_job_12345"
    set_job_state(
        job_id,
        {
            "job_id": job_id,
            "status": "running",
            "step_id": "embed",
            "message": "Generating Embeddings",
            "progress": 50,
            "stats": {"chunks_processed": 100},
            "repo": {"owner": "fastapi", "name": "fastapi"},
        },
    )

    # 1. Poll running state
    res_running = client.get(f"/api/v1/analyze/{job_id}")
    assert res_running.status_code == 202
    data_running = res_running.json()
    assert data_running["status"] == "running"
    assert data_running["step_id"] == "embed"
    assert data_running["progress"] == 50

    # 2. Update to completed state
    set_job_state(
        job_id,
        {
            "job_id": job_id,
            "status": "completed",
            "progress": 100,
            "result": {"summary": "Analysis completed"},
            "repo": {"owner": "fastapi", "name": "fastapi"},
        },
    )

    res_completed = client.get(f"/api/v1/analyze/{job_id}")
    assert res_completed.status_code == 200
    data_completed = res_completed.json()
    assert data_completed["status"] == "completed"
    assert data_completed["progress"] == 100
    assert data_completed["result"] == {"summary": "Analysis completed"}


def test_get_analyze_status_failed(client):
    """GET /api/v1/analyze/{job_id} returns 500 when failed."""
    job_id = "test_job_failed_123"
    set_job_state(
        job_id,
        {
            "job_id": job_id,
            "status": "failed",
            "error": "Repository not found or access denied.",
            "repo": {"owner": "invalid", "name": "repo"},
        },
    )

    res_failed = client.get(f"/api/v1/analyze/{job_id}")
    assert res_failed.status_code == 500
    data_failed = res_failed.json()
    assert data_failed["status"] == "failed"
    assert "not found" in data_failed["error"]


def test_execute_repository_analysis_invokes_callback(tmp_path):
    """Verify execute_repository_analysis executes stages and invokes progress callback."""
    repo_url = "https://github.com/mock/repo"
    local_dir = tmp_path / "mock_repo"
    local_dir.mkdir()
    (local_dir / "main.py").write_text("def hello(): pass", encoding="utf-8")

    progress_events = []

    def on_progress(event):
        progress_events.append(event)

    with (
        patch(
            "backend.routers.repositories.github_service.clone_repository",
            return_value=str(local_dir),
        ),
        patch(
            "backend.routers.repositories.detect_tech_stack_and_deps",
            return_value=(["Python"], []),
        ),
        patch(
            "backend.routers.repositories.embedding_service.generate_embeddings",
            return_value=[[0.1] * 384],
        ),
        patch(
            "backend.routers.repositories.chroma_store.stage_repository_batch",
            return_value=1,
        ),
        patch("backend.routers.repositories.chroma_store.publish_repository_version"),
        patch("backend.routers.repositories.symbol_service.build_full"),
        patch(
            "backend.routers.repositories.architecture_service.build_full",
            return_value={},
        ),
        patch(
            "backend.routers.repositories.call_graph_service.build",
            return_value=iter([]),
        ),
        patch(
            "backend.routers.repositories.api_surface_service.build",
            return_value=iter([]),
        ),
        patch(
            "backend.routers.repositories.generate_architecture_summary",
            return_value=MagicMock(model_dump=lambda: {}),
        ),
        patch("backend.routers.repositories.snapshot_store.save"),
        patch("backend.routers.repositories._persist_analysis_store"),
        patch(
            "backend.routers.repositories.engineering_memory_service.create_snapshot"
        ),
    ):
        result = execute_repository_analysis(
            repo_url=repo_url,
            branch="main",
            force_rebuild=False,
            progress_callback=on_progress,
            request_id="req-123",
        )

        assert result["repo"] == "mock/repo"
        assert len(progress_events) >= 5
        step_ids = [e["step_id"] for e in progress_events]
        assert "clone" in step_ids
        assert "detect" in step_ids
        assert "parse" in step_ids
        assert "embed" in step_ids
        assert "index" in step_ids
        assert "analyze" in step_ids
        assert "answer" in step_ids
