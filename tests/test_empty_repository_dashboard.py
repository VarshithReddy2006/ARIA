"""Regression tests for post-analysis dashboard endpoints on empty / zero-node repositories.

Ensures that repositories with zero source code symbols or zero dependency graph nodes
(e.g., README-only repositories like octocat/Hello-World) produce valid, structured
HTTP 200 responses with clean empty states rather than 404/500 errors.
"""

import networkx as nx
import pytest
from fastapi.testclient import TestClient

from backend.api import app
from models.phase2 import ImpactAnalysis, ReadingOrder
from services.graph_service import GraphService
from services.impact_analysis_service import ImpactAnalysisService
from services.reading_order_service import ReadingOrderService


@pytest.fixture
def clean_graph_service(tmp_path, monkeypatch):
    """Provide an isolated GraphService using tmp_path for storage."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    svc = GraphService()
    return svc


class TestEmptyRepositoryDashboard:
    """Test dashboard backend services on zero-node repository graphs."""

    def test_reading_order_zero_node_with_standalone_files(self, tmp_path, monkeypatch):
        """Reading order returns fallback file list when graph is empty but files exist."""
        repo_name = "test-owner/readme-repo"
        graph_svc = GraphService()
        empty_graph = nx.DiGraph()
        graph_svc.save_graph(empty_graph, repo_name)

        # Mock ANALYSIS_STORE to contain a standalone README.md file
        from backend.dependencies import ANALYSIS_STORE

        ANALYSIS_STORE[repo_name] = {
            "analysis": {
                "structure": {
                    ".": ["README.md", "LICENSE"],
                }
            }
        }

        ro_svc = ReadingOrderService(
            graph_service=graph_svc, analysis_store=ANALYSIS_STORE
        )
        result = ro_svc.generate_reading_order(repo_name)

        assert isinstance(result, ReadingOrder)
        assert result.repo == repo_name
        assert len(result.ordered_files) == 2
        assert result.ordered_files[0].file_path == "LICENSE"
        assert result.ordered_files[1].file_path == "README.md"
        assert result.total_files_ranked == 2
        assert result.estimated_reading_time == 1

    def test_reading_order_zero_node_empty_repo(self, tmp_path, monkeypatch):
        """Reading order returns empty model when graph has 0 nodes and 0 files."""
        repo_name = "test-owner/completely-empty-repo"
        graph_svc = GraphService()
        empty_graph = nx.DiGraph()
        graph_svc.save_graph(empty_graph, repo_name)

        from backend.dependencies import ANALYSIS_STORE

        ANALYSIS_STORE.pop(repo_name, None)

        ro_svc = ReadingOrderService(graph_service=graph_svc)
        result = ro_svc.generate_reading_order(repo_name)

        assert isinstance(result, ReadingOrder)
        assert result.repo == repo_name
        assert len(result.ordered_files) == 0
        assert result.total_files_ranked == 0
        assert "No reading path can be generated" in result.reasoning[0]

    def test_reading_order_unbuilt_graph_raises_value_error(self):
        """Reading order raises ValueError with actionable message when graph does not exist."""
        ro_svc = ReadingOrderService()
        with pytest.raises(ValueError) as excinfo:
            ro_svc.generate_reading_order("nonexistent/repo-999")
        assert "Please analyze the repository first" in str(excinfo.value)

    def test_impact_analysis_zero_node_graph(self):
        """Impact analysis returns clean zero-impact model on zero-node graph."""
        repo_name = "test-owner/zero-node-impact"
        graph_svc = GraphService()
        empty_graph = nx.DiGraph()
        graph_svc.save_graph(empty_graph, repo_name)

        ia_svc = ImpactAnalysisService(graph_service=graph_svc)
        result = ia_svc.analyze_change(repo_name, "Add GitHub OAuth Login")

        assert isinstance(result, ImpactAnalysis)
        assert result.repo == repo_name
        assert len(result.directly_affected_files) == 0
        assert len(result.indirectly_affected_files) == 0
        assert result.confidence == 0
        assert result.risk_level == "low"
        assert result.estimated_file_count == 0

    def test_impact_analysis_unbuilt_graph_raises_value_error(self):
        """Impact analysis raises ValueError when graph does not exist."""
        ia_svc = ImpactAnalysisService()
        with pytest.raises(ValueError) as excinfo:
            ia_svc.analyze_change("nonexistent/repo-999", "Refactor models")
        assert "Please analyze the repository first" in str(excinfo.value)

    def test_graph_full_endpoint_zero_nodes_returns_200(self):
        """GET /api/v1/graph/{owner}/{repo}/full returns HTTP 200 with empty nodes on zero-node graph."""
        repo_name = "octocat/hello-zero"
        graph_svc = GraphService()
        empty_graph = nx.DiGraph()
        graph_svc.save_graph(empty_graph, repo_name)

        client = TestClient(app)
        res = client.get("/api/v1/graph/octocat/hello-zero/full")
        assert res.status_code == 200
        data = res.json()
        assert "nodes" in data
        assert len(data["nodes"]) == 0
        assert "edges" in data
        assert len(data["edges"]) == 0

    def test_architecture_graph_endpoint_zero_nodes_returns_200(self):
        """GET /api/v1/architecture/{owner}/{repo}/graph returns HTTP 200 on zero-node graph."""
        repo_name = "octocat/hello-arch-zero"
        graph_svc = GraphService()
        empty_graph = nx.DiGraph()
        graph_svc.save_graph(empty_graph, repo_name)

        client = TestClient(app)
        res = client.get("/api/v1/architecture/octocat/hello-arch-zero/graph")
        assert res.status_code == 200
        data = res.json()
        assert "nodes" in data
        assert len(data["nodes"]) == 0

    def test_graph_full_endpoint_missing_graph_returns_404(self):
        """GET /api/v1/graph/{owner}/{repo}/full returns 404 when repository was never analyzed."""
        client = TestClient(app)
        res = client.get("/api/v1/graph/nonexistent-owner/unindexed-repo/full")
        assert res.status_code == 404
        assert "Please analyze the repository first" in res.json()["detail"]

    def test_reading_order_endpoint_zero_node_returns_200(self):
        """POST /api/v1/reading-order returns HTTP 200 for zero-node analyzed repo."""
        repo_name = "octocat/hello-reading-zero"
        graph_svc = GraphService()
        empty_graph = nx.DiGraph()
        graph_svc.save_graph(empty_graph, repo_name)

        client = TestClient(app)
        res = client.post("/api/v1/reading-order", json={"repo": repo_name})
        assert res.status_code == 200
        data = res.json()
        assert data["repo"] == repo_name
        assert isinstance(data["ordered_files"], list)

    def test_impact_analysis_endpoint_zero_node_returns_200(self):
        """POST /api/v1/impact-analysis returns HTTP 200 for zero-node analyzed repo."""
        repo_name = "octocat/hello-impact-zero"
        graph_svc = GraphService()
        empty_graph = nx.DiGraph()
        graph_svc.save_graph(empty_graph, repo_name)

        client = TestClient(app)
        res = client.post(
            "/api/v1/impact-analysis",
            json={"repo": repo_name, "issue": "Add dark mode toggle"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["repo"] == repo_name
        assert data["directly_affected_files"] == []
        assert data["indirectly_affected_files"] == []
