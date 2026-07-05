"""Unit tests for the Repository Knowledge Graph architecture, builder, navigator, and endpoints."""

import sys
import os
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# Ensure root directory is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.api import app
from models.knowledge_graph import (
    KnowledgeGraph,
    KnowledgeGraphNode,
    KnowledgeGraphEdge,
    KnowledgeGraphSummary,
)
from services.knowledge_graph_builder import RepositoryKnowledgeGraphBuilder
from services.knowledge_graph_navigator import RepositoryKnowledgeGraphNavigator

client = TestClient(app)


def test_knowledge_graph_models() -> None:
    """Verifies that Knowledge Graph Pydantic models can be instantiated and validated."""
    node = KnowledgeGraphNode(id="repo1", type="repository", properties={"name": "test-repo"})
    edge = KnowledgeGraphEdge(source="repo1", target="repo1::health", type="HAS_HEALTH")
    kg = KnowledgeGraph(repository_name="test-owner/test-repo", nodes=[node], edges=[edge])

    assert kg.repository_name == "test-owner/test-repo"
    assert len(kg.nodes) == 1
    assert kg.nodes[0].id == "repo1"
    assert kg.edges[0].type == "HAS_HEALTH"


@patch("backend.dependencies.symbol_service")
@patch("backend.dependencies.graph_service")
@patch("backend.dependencies.repository_twin_builder")
def test_knowledge_graph_builder_and_navigator(mock_tb, mock_gs, mock_ss) -> None:
    """Verifies that KnowledgeGraphBuilder correctly composes state and navigator navigates correctly."""
    repo_name = "test-owner/test-repo"

    # Mock Twin
    mock_twin = MagicMock()
    mock_twin.metadata = {"tech_stack": ["Python"], "total_loc": 100}
    mock_twin.files = ["main.py", "utils.py"]
    mock_twin.health_summary = {"overall_score": 90.0, "grade": "A", "breakdown": {}}
    mock_twin.compliance_summary = {"status": "compliant", "reasons": [], "dead_code_ratio": 0.0}
    mock_twin.architecture_summary = {"cycles_count": 0, "strongly_connected_components": 1}
    mock_twin.symbols_summary = {"total_symbols": 0}
    mock_tb.build_twin.return_value = mock_twin

    # Mock Symbol Service
    mock_ss.load.return_value = MagicMock(symbols=[])

    # Mock Dependency Graph Service
    mock_dep_graph = MagicMock()
    mock_dep_graph.edges.return_value = [("main.py", "utils.py")]
    mock_gs.load_graph.return_value = mock_dep_graph

    # 1. Test Builder
    mock_cache = MagicMock()
    mock_cache.get.return_value = None
    builder = RepositoryKnowledgeGraphBuilder(
        twin_builder=mock_tb,
        cache=mock_cache,
    )

    kg = builder.build_graph(repo_name)
    assert kg.repository_name == repo_name
    
    # Assert nodes presence
    node_ids = {node.id for node in kg.nodes}
    assert repo_name in node_ids
    assert f"{repo_name}::health" in node_ids
    assert f"{repo_name}::compliance" in node_ids
    assert f"{repo_name}::main.py" in node_ids
    assert f"{repo_name}::utils.py" in node_ids

    # Assert edges presence
    edge_types = {edge.type for edge in kg.edges}
    assert "HAS_HEALTH" in edge_types
    assert "HAS_COMPLIANCE" in edge_types
    assert "CONTAINS" in edge_types
    assert "IMPORTS" in edge_types

    summary = builder.build_graph_summary(repo_name)
    assert summary.repository_name == repo_name
    assert summary.nodes_count > 0
    assert summary.node_types_breakdown["repository"] == 1

    # 2. Test Navigator
    navigator = RepositoryKnowledgeGraphNavigator(builder=builder)

    # find_node
    node = navigator.find_node(repo_name, repo_name)
    assert node is not None
    assert node.type == "repository"

    # find_neighbors
    neighbors = navigator.find_neighbors(repo_name, repo_name)
    neighbor_ids = {n.id for n in neighbors}
    assert f"{repo_name}::health" in neighbor_ids

    # find_shortest_path
    path = navigator.find_shortest_path(repo_name, repo_name, f"{repo_name}::main.py")
    assert len(path) == 2
    assert path[0] == repo_name
    assert path[1] == f"{repo_name}::main.py"

    # find_impact
    impact = navigator.find_impact(repo_name, f"{repo_name}::main.py")
    assert f"{repo_name}::utils.py" in impact


def test_knowledge_graph_endpoints() -> None:
    """Verifies that HTTP endpoints for knowledge-graph work correctly with mocks."""
    repo_name = "test-owner/test-repo"

    with (
        patch("backend.routers.knowledge_graph.repository_knowledge_graph_builder") as mock_builder,
        patch("backend.routers.knowledge_graph.repository_knowledge_graph_navigator") as mock_navigator,
    ):
        mock_builder.build_graph.return_value = KnowledgeGraph(
            repository_name=repo_name,
            nodes=[KnowledgeGraphNode(id=repo_name, type="repository")],
            edges=[],
        )
        mock_builder.build_graph_summary.return_value = KnowledgeGraphSummary(
            repository_name=repo_name,
            nodes_count=1,
            edges_count=0,
            node_types_breakdown={"repository": 1},
            edge_types_breakdown={},
        )
        mock_builder.twin_builder.store = {repo_name: {}}

        # Test full KG route
        response = client.get("/api/repositories/test-owner/test-repo/knowledge-graph")
        assert response.status_code == 200
        assert response.json()["repository_name"] == repo_name

        # Test KG summary route
        response_summary = client.get("/api/repositories/test-owner/test-repo/knowledge-graph/summary")
        assert response_summary.status_code == 200
        assert response_summary.json()["nodes_count"] == 1

        # Test versioned v1 route
        response_v1 = client.get("/api/v1/repositories/test-owner/test-repo/knowledge-graph/summary")
        assert response_v1.status_code == 200
        assert response_v1.json()["nodes_count"] == 1
