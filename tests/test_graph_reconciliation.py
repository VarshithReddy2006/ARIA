"""Graph Reconciliation Invariant Test — R-011.

Asserts that node and edge counts for a fixture repository are identical
across all services and endpoints that report them:
1. GraphService.load_graph(repo_name)
2. RepositoryTwinBuilder.build_twin(repo_name)
3. GraphSerializer.get_full_graph(repo_name)
"""

import pytest
import networkx as nx
from fastapi.testclient import TestClient

from backend.api import app
from backend.dependencies import (
    ANALYSIS_STORE,
    get_graph_service,
    get_repository_twin_builder,
    get_graph_serializer,
)
from models.schemas import RepositoryAnalysis, ArchitectureSummary


client = TestClient(app)


@pytest.fixture
def setup_reconciliation_fixture(tmp_path):
    """Sets up a test repository graph and ANALYSIS_STORE entry for reconciliation testing."""
    repo_name = "test-owner/reconcile-repo"
    graph_service = get_graph_service()

    # Build a known NetworkX graph
    g = nx.DiGraph()
    g.add_node("services/a.py", language="python", type="file")
    g.add_node("services/b.py", language="python", type="file")
    g.add_node("services/c.py", language="python", type="file")
    g.add_edge("services/a.py", "services/b.py", relationship="imports")
    g.add_edge("services/b.py", "services/c.py", relationship="imports")

    graph_service.save_graph(g, repo_name)

    # Populate ANALYSIS_STORE
    analysis_data = RepositoryAnalysis(
        structure={"services": ["a.py", "b.py", "c.py"]},
        dependencies=["networkx"],
        tech_stack=["python"],
        metadata={"loc": "150", "commits_count": "10"},
    )
    architecture_data = ArchitectureSummary(
        summary="Test architecture",
        reading_order=["services/a.py", "services/b.py", "services/c.py"],
        relationships=[],
    )
    ANALYSIS_STORE[repo_name] = {
        "analysis": analysis_data,
        "architecture": architecture_data,
    }

    yield repo_name, g


def test_graph_node_and_edge_counts_reconciled(setup_reconciliation_fixture):
    """Verify node and edge count consistency across GraphService, TwinBuilder, and Serializer."""
    repo_name, raw_graph = setup_reconciliation_fixture

    # 1. Canonical GraphService
    graph_service = get_graph_service()
    loaded_graph = graph_service.load_graph(repo_name)
    assert loaded_graph is not None
    canonical_nodes = loaded_graph.number_of_nodes()
    canonical_edges = loaded_graph.number_of_edges()

    assert canonical_nodes == 3
    assert canonical_edges == 2

    # 2. Repository Twin Builder
    twin_builder = get_repository_twin_builder()
    twin_builder.store = ANALYSIS_STORE
    twin = twin_builder.build_twin(repo_name)

    twin_nodes = twin.architecture_summary["dependency_nodes_count"]
    twin_edges = twin.architecture_summary["import_relationships_count"]

    assert twin_nodes == canonical_nodes, (
        f"Twin nodes {twin_nodes} != canonical {canonical_nodes}"
    )
    assert twin_edges == canonical_edges, (
        f"Twin edges {twin_edges} != canonical {canonical_edges}"
    )

    # 3. Graph Serializer
    serializer = get_graph_serializer()
    serializer_data = serializer.get_full_graph(repo_name)
    serializer_nodes = len(serializer_data.get("nodes", []))
    serializer_edges = len(serializer_data.get("edges", []))

    assert serializer_nodes == canonical_nodes, (
        f"Serializer nodes {serializer_nodes} != canonical {canonical_nodes}"
    )
    assert serializer_edges == canonical_edges, (
        f"Serializer edges {serializer_edges} != canonical {canonical_edges}"
    )

    # 4. HTTP API Endpoint /api/v1/graph/{owner}/{repo}/full
    resp = client.get(f"/api/v1/graph/{repo_name}/full")
    assert resp.status_code == 200
    api_data = resp.json()
    api_nodes = len(api_data.get("nodes", []))
    api_edges = len(api_data.get("edges", []))

    assert api_nodes == canonical_nodes, (
        f"API nodes {api_nodes} != canonical {canonical_nodes}"
    )
    assert api_edges == canonical_edges, (
        f"API edges {api_edges} != canonical {canonical_edges}"
    )
