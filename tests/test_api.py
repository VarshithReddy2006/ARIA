"""Unit tests for the FastAPI backend endpoints."""

import sys
import os
import json
from unittest.mock import patch
from fastapi.testclient import TestClient

# Ensure root directory is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.api import app

client = TestClient(app)


def test_get_examples() -> None:
    """Verifies example repos list is returned correctly."""
    response = client.get("/api/repos/examples")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert "name" in data[0]
    assert "url" in data[0]


def test_get_recent() -> None:
    """Verifies recent repos list returns empty or populated list."""
    response = client.get("/api/repos/recent")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_map_issue() -> None:
    """Verifies issue mapping endpoint works and returns plan structure."""
    payload = {
        "repo": "test/repo",
        "title": "Fix memory leaks in cache",
        "description": "The cache store is leaking reference counts.",
    }
    response = client.post("/api/issues/map", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "issue_summary" in data
    assert "relevant_files" in data
    assert "implementation_plan" in data
    assert "issue_type" in data
    assert "complexity" in data
    assert "confidence" in data
    assert "verified" in data
    assert "sources" in data
    assert "affected_components" in data


def test_index_invalid_repo_url_returns_400() -> None:
    """Invalid GitHub repo URL should not crash and should return 4xx."""
    response = client.post("/api/index", json={"repo_url": "hello"})
    assert response.status_code in (400, 422)


def test_index_nonexistent_repo_returns_404() -> None:
    """Nonexistent repository should map to 404 not 500."""
    response = client.post(
        "/api/index",
        json={
            "repo_url": "https://github.com/this-repo-should-not-exist-1234567890/does-not-exist"
        },
    )
    # Depending on environment/network, 404 mapping should happen; otherwise this test may fail.
    assert response.status_code in (404,)


def test_analyze_repository_success() -> None:
    """Verifies analyze endpoint works end-to-end and returns correct schema."""
    with (
        patch("backend.routers.repositories.github_service") as mock_gh,
        patch("backend.routers.repositories.embedding_service") as mock_embed,
        patch("backend.routers.repositories.chroma_store"),
        patch("backend.routers.repositories.symbol_service"),
        patch("backend.routers.repositories.architecture_service") as mock_arch,
        patch("backend.dependencies.call_graph_service") as mock_call,
        patch("backend.dependencies.api_surface_service") as mock_api,
        patch(
            "backend.routers.repositories.generate_architecture_summary"
        ) as mock_summary,
        patch("backend.routers.repositories.snapshot_store") as mock_store,
        patch("backend.routers.repositories._persist_analysis_store"),
    ):
        mock_gh.clone_repository.return_value = "/dummy/path"
        mock_gh.extract_source_files.return_value = [
            {"path": "main.py", "content": "print('hello')"}
        ]
        mock_store.load.return_value = None
        mock_embed.generate_embeddings.return_value = [[0.1] * 1536]
        mock_arch.build_full.return_value = {
            "files_parsed": 1,
            "dependencies_found": 0,
            "entry_points": [],
        }
        mock_call.build_full.return_value = []
        mock_api.build_full.return_value = []

        from models.schemas import ArchitectureSummary

        mock_summary.return_value = ArchitectureSummary(
            summary="Dummy summary", reading_order=[], relationships=[]
        )

        payload = {"url": "https://github.com/test-owner/test-repo", "branch": "main"}

        response = client.post("/api/analyze", json=payload)
        assert response.status_code == 200

        events = []
        for line in response.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        assert any(e.get("status") == "complete" for e in events)
        done_event = next(e for e in events if e.get("status") == "done")
        assert done_event["repo"] == "test-owner/test-repo"

        # Verify frontend parser accepts response and extracts correct owner/repo
        repo_path = (
            done_event.get("repo")
            or done_event.get("repository")
            or (
                done_event.get("owner")
                and done_event.get("repo_name")
                and f"{done_event.get('owner')}/{done_event.get('repo_name')}"
            )
        )
        assert repo_path is not None, (
            "Frontend parser would reject: missing repo in analysis result"
        )

        parts = repo_path.split("/")
        assert len(parts) == 2
        owner, repo = parts
        assert owner == "test-owner"
        assert repo == "test-repo"

        # Verify navigation URL generates correctly
        nav_url = f"/analysis?owner={owner}&repo={repo}"
        assert nav_url == "/analysis?owner=test-owner&repo=test-repo"

        # Verify repository loads after analysis
        response_detail = client.get(f"/api/analysis/{owner}/{repo}")
        assert response_detail.status_code == 200
        detail_data = response_detail.json()
        assert "analysis" in detail_data
        assert "architecture" in detail_data


def test_analyze_repository_failure() -> None:
    """Verifies analyze endpoint handles exceptions gracefully by yielding status: error and status: done."""
    with (
        patch("backend.routers.repositories.github_service") as mock_gh,
        patch("backend.routers.repositories.snapshot_store"),
    ):
        mock_gh.clone_repository.side_effect = Exception("Mock clone error")

        payload = {"url": "https://github.com/test-owner/test-repo", "branch": "main"}
        response = client.post("/api/analyze", json=payload)
        assert response.status_code == 200

        events = []
        for line in response.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        assert any(e.get("status") == "error" for e in events)
        error_event = next(e for e in events if e.get("status") == "error")
        # Raw exception text stays in server logs only; clients receive the
        # structured, sanitized error envelope.
        assert "Mock clone error" not in error_event["message"]
        assert "An unexpected internal error occurred." in error_event["message"]
        assert "Stage:" in error_event["message"]

        done_event = next(e for e in events if e.get("status") == "done")
        assert "repo" not in done_event


def test_chat_reload_resolves_pipeline_without_attribute_error() -> None:
    """Regression test for H-1: /chat/reload must not raise AttributeError.

    The endpoint previously referenced `dependencies._retrieval_pipeline`
    which does not exist in the module, causing a silent failure or crash.
    This test verifies:
      1. The endpoint does not raise AttributeError.
      2. When a retrieval pipeline exists, the ProviderManager is replaced.
      3. The endpoint returns a structured response (success or provider error).
    """
    from backend import dependencies
    from unittest.mock import AsyncMock, MagicMock

    # Simulate a cached retrieval pipeline with a ProviderManager
    mock_pipeline = MagicMock()
    mock_pipeline.provider_manager = MagicMock()
    original_pm = mock_pipeline.provider_manager

    with patch.dict(dependencies._SINGLETONS, {"retrieval_pipeline": mock_pipeline}):
        with patch(
            "services.llm.provider_factory.ProviderFactory.get_provider"
        ) as mock_get:
            mock_provider = AsyncMock()
            mock_provider.generate = AsyncMock(return_value="ready")
            mock_get.return_value = mock_provider

            response = client.post("/api/v1/chat/reload")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    # Verify the ProviderManager was replaced (not the original instance)
    assert mock_pipeline.provider_manager is not original_pm


def test_openapi_version_matches_release() -> None:
    """M-2 regression: OpenAPI metadata must report the current release version."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["version"] == "1.5.0"
