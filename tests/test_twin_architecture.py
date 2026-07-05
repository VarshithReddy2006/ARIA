"""Unit tests for the Repository Digital Twin architecture, builder, navigator, and endpoints."""

import sys
import os
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# Ensure root directory is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.api import app
from models.twin import RepositoryTwin, RepositoryTwinSummary, RepositorySnapshot
from services.twin_builder import RepositoryTwinBuilder
from services.twin_navigator import RepositoryTwinNavigator

client = TestClient(app)


def test_twin_models() -> None:
    """Verifies that the Repository Twin Pydantic models can be instantiated and validated."""
    snapshot = RepositorySnapshot(
        commit_sha="abc123def456",
        branch="main",
        indexed_timestamp=1700000000.0,
        analysis_version="1.0.0",
    )

    twin = RepositoryTwin(
        repository_name="test-owner/test-repo",
        snapshot=snapshot,
        metadata={"tech_stack": ["Python"], "total_loc": 100, "commits_count": 10},
        files=["main.py", "utils.py"],
        symbols_summary={"total_symbols": 5, "public_symbols": 4, "private_symbols": 1, "public_private_ratio": 4.0},
        dependencies_summary={"dependencies": [], "import_relationships_count": 1, "dependency_nodes_count": 2},
        architecture_summary={"summary": "Simple app", "cycles_count": 0, "strongly_connected_components": 1, "entry_points": ["main.py"], "reading_order": ["utils.py", "main.py"]},
        health_summary={"overall_score": 95.0, "grade": "A", "breakdown": {"architecture": 100.0, "api": 90.0, "hygiene": 95.0, "churn": 100.0, "readability": 90.0}},
        compliance_summary={"status": "compliant", "reasons": [], "has_license": True, "cycles_count": 0, "dead_code_ratio": 0.0},
    )

    assert twin.repository_name == "test-owner/test-repo"
    assert twin.snapshot.commit_sha == "abc123def456"
    assert "Python" in twin.metadata["tech_stack"]


@patch("backend.dependencies.symbol_service")
@patch("backend.dependencies.graph_service")
@patch("backend.dependencies.architecture_service")
@patch("backend.dependencies.report_composer")
@patch("backend.dependencies.dead_code_service")
@patch("backend.dependencies.github_service")
@patch("backend.dependencies.snapshot_store")
def test_twin_builder_and_navigator(
    mock_store, mock_gh, mock_dcs, mock_rc, mock_arch, mock_gs, mock_ss
) -> None:
    """Verifies that the twin builder correctly aggregates state and navigator delegates query methods."""
    repo_name = "test-owner/test-repo"
    local_path = "/dummy/path/test-owner_test-repo"

    # Setup mocks
    mock_gh.get_local_repo_path.return_value = local_path
    mock_store.load.return_value = {
        "repository_hash": "abc123def",
        "last_successful_build": 1700000000.0,
        "application_version": "1.0.0",
        "file_hashes": {"main.py": "hash1", "utils.py": "hash2"},
    }

    mock_analysis_entry = {
        "analysis": MagicMock(
            metadata={"loc": "100", "commits_count": "10"},
            tech_stack=["Python"],
            dependencies=["fastapi"],
        ),
        "architecture": MagicMock(
            summary="Test architecture",
            entry_points=["main.py"],
            reading_order=["utils.py", "main.py"],
        ),
    }

    from models.symbol import Symbol
    mock_ss.load.return_value = MagicMock(
        symbol_count=2,
        symbols=[
            Symbol(name="start_server", file_path="main.py", type="function", line_number=10, language="python"),
            Symbol(name="_internal_helper", file_path="utils.py", type="function", line_number=5, language="python"),
        ],
    )

    mock_dep_graph = MagicMock()
    mock_dep_graph.number_of_nodes.return_value = 2
    mock_dep_graph.number_of_edges.return_value = 1
    mock_dep_graph.has_node.return_value = True
    mock_dep_graph.successors.return_value = ["utils.py"]
    mock_dep_graph.predecessors.return_value = ["main.py"]
    mock_gs.load_graph.return_value = mock_dep_graph

    mock_report = MagicMock()
    mock_report.scores = MagicMock(
        overall=92.5,
        grade="A",
        architecture=100.0,
        api=90.0,
        hygiene=95.0,
        churn=85.0,
        readability=90.0,
    )
    mock_rc.compose_report.return_value = mock_report

    mock_dcs.analyze.return_value = MagicMock(unused_files=[])

    # 1. Test Builder
    store = {repo_name: mock_analysis_entry}
    builder = RepositoryTwinBuilder(
        store=store,
        symbol_service=mock_ss,
        graph_service=mock_gs,
        architecture_service=mock_arch,
        report_composer=mock_rc,
        dead_code_service=mock_dcs,
        github_service=mock_gh,
        snapshot_store=mock_store,
    )

    twin = builder.build_twin(repo_name)
    assert twin.repository_name == repo_name
    assert twin.snapshot.commit_sha == "abc123def"
    assert twin.metadata["total_loc"] == 100
    assert twin.symbols_summary["total_symbols"] == 2
    assert twin.symbols_summary["public_symbols"] == 1
    assert twin.symbols_summary["private_symbols"] == 1
    assert twin.symbols_summary["public_private_ratio"] == 1.0
    assert twin.dependencies_summary["dependencies"] == ["fastapi"]
    assert twin.architecture_summary["summary"] == "Test architecture"
    assert twin.health_summary["overall_score"] == 92.5
    assert twin.compliance_summary["status"] == "warning"  # due to missing license file

    summary = builder.build_twin_summary(repo_name)
    assert summary.repository_name == repo_name
    assert summary.overall_health_score == 92.5
    assert summary.compliance_status == "warning"
    assert summary.total_files == 2

    # 2. Test Navigator
    navigator = RepositoryTwinNavigator(
        symbol_service=mock_ss,
        graph_service=mock_gs,
        architecture_service=mock_arch,
        report_composer=mock_rc,
        github_service=mock_gh,
        twin_builder=builder,
    )

    # findSymbol
    mock_ss.get_definition.return_value = Symbol(name="start_server", type="function", file_path="main.py", line_number=10, language="python")
    mock_ss.get_references.return_value = [Symbol(name="start_server", type="function", file_path="main.py", line_number=10, language="python")]
    sym_res = navigator.find_symbol(repo_name, "start_server")
    assert sym_res["symbol_name"] == "start_server"
    assert sym_res["definition"]["name"] == "start_server"
    assert len(sym_res["references"]) == 1

    # findDependencies / findDependents
    deps = navigator.find_dependencies(repo_name, "main.py")
    assert deps == ["utils.py"]
    dependents = navigator.find_dependents(repo_name, "utils.py")
    assert dependents == ["main.py"]


def test_twin_endpoints() -> None:
    """Verifies that the /twin and /twin/summary router endpoints are active and return correctly."""
    repo_name = "test-owner/test-repo"

    with (
        patch("backend.routers.twin.repository_twin_builder") as mock_builder,
        patch("backend.routers.twin.repository_twin_navigator") as mock_navigator,
    ):
        snapshot_dto = RepositorySnapshot(
            commit_sha="123456",
            branch="main",
            indexed_timestamp=1700000000.0,
            analysis_version="1.0.0",
        )

        # Mock full twin
        mock_builder.build_twin.return_value = RepositoryTwin(
            repository_name=repo_name,
            snapshot=snapshot_dto,
            metadata={"tech_stack": ["Python"], "total_loc": 100, "commits_count": 10},
            files=["main.py"],
            symbols_summary={"total_symbols": 1, "public_symbols": 1, "private_symbols": 0, "public_private_ratio": 1.0},
            dependencies_summary={"dependencies": [], "import_relationships_count": 0, "dependency_nodes_count": 1},
            architecture_summary={"summary": "App", "cycles_count": 0, "strongly_connected_components": 1, "entry_points": [], "reading_order": []},
            health_summary={"overall_score": 90.0, "grade": "A", "breakdown": {"architecture": 90.0, "api": 90.0, "hygiene": 90.0, "churn": 90.0, "readability": 90.0}},
            compliance_summary={"status": "compliant", "reasons": [], "has_license": True, "cycles_count": 0, "dead_code_ratio": 0.0},
        )

        # Mock summary
        mock_builder.build_twin_summary.return_value = RepositoryTwinSummary(
            repository_name=repo_name,
            snapshot=snapshot_dto,
            tech_stack=["Python"],
            overall_health_score=90.0,
            health_grade="A",
            compliance_status="compliant",
            total_files=1,
            total_symbols=1,
        )

        # Test full twin route
        response = client.get("/api/repositories/test-owner/test-repo/twin")
        assert response.status_code == 200
        data = response.json()
        assert data["repository_name"] == repo_name
        assert data["snapshot"]["commit_sha"] == "123456"

        # Test twin summary route
        response_summary = client.get("/api/repositories/test-owner/test-repo/twin/summary")
        assert response_summary.status_code == 200
        summary_data = response_summary.json()
        assert summary_data["repository_name"] == repo_name
        assert summary_data["overall_health_score"] == 90.0

        # Test versioned v1 route
        response_v1 = client.get("/api/v1/repositories/test-owner/test-repo/twin/summary")
        assert response_v1.status_code == 200
        assert response_v1.json()["overall_health_score"] == 90.0
