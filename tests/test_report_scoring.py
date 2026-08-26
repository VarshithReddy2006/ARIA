import json
from unittest.mock import MagicMock
import pytest

import networkx as nx

from models.report import ReportDataModel
from services.report.composer import ReportComposer
from storage.migrations import run_migrations, get_db_connection


@pytest.fixture(autouse=True)
def run_db_migrations():
    """Initializes migrations before running report tests."""
    run_migrations()


def test_score_calculation_perfect_repo():
    # Mock services to represent a perfectly clean repository
    mock_symbol = MagicMock()
    mock_symbol.symbol_count = 100
    mock_symbol.symbols = [
        MagicMock(name=f"func_{i}", type="function") for i in range(100)
    ]
    for i, s in enumerate(mock_symbol.symbols):
        s.name = f"func_{i}"

    mock_symbol_service = MagicMock()
    mock_symbol_service.load.return_value = mock_symbol

    mock_dead_code = MagicMock()
    mock_dead_code.unused_files = []
    mock_dead_code_service = MagicMock()
    mock_dead_code_service.analyze.return_value = mock_dead_code

    mock_churn = MagicMock()
    mock_churn.hotspots = []
    mock_churn.file_records = [MagicMock() for _ in range(50)]
    mock_git_history_service = MagicMock()
    mock_git_history_service.load.return_value = mock_churn

    # Graph with no cycles, 0 strongly connected components
    mock_graph = nx.DiGraph()
    # Add some nodes
    mock_graph.add_node("a.py")
    mock_graph.add_node("b.py")
    mock_graph.add_edge("a.py", "b.py")

    mock_graph_service = MagicMock()
    mock_graph_service.load_graph.return_value = mock_graph

    # Mock ANALYSIS_STORE entry
    mock_analysis = MagicMock()
    mock_analysis.metadata = {"loc": "1200", "commits_count": "45"}
    mock_analysis.tech_stack = ["python"]

    mock_architecture = MagicMock()
    # 5 files in reading path
    mock_architecture.reading_order = ["a.py", "b.py"]

    store = {
        "org/perfect": {"analysis": mock_analysis, "architecture": mock_architecture}
    }

    composer = ReportComposer(
        store=store,
        symbol_service=mock_symbol_service,
        call_graph_service=MagicMock(),
        dead_code_service=mock_dead_code_service,
        git_history_service=mock_git_history_service,
        graph_service=mock_graph_service,
    )

    report = composer.compose_report("org/perfect")

    assert isinstance(report, ReportDataModel)
    assert report.metadata.repo_name == "org/perfect"
    assert report.metadata.total_loc == 1200
    assert report.metadata.commits_count == 45

    # Check scores:
    # cycles = 0, SCCs = 1 (nx.strongly_connected_components returns 2 for 2 isolated file nodes/DiGraph components)
    # math.exp(-0.1 * (0 + 3 * 2)) = exp(-0.6) = 0.5488 -> S_arch should be ~54.9
    assert report.scores.architecture > 0
    # Hygiene has 0 smells, 0 dead files -> S_hygiene = 100 * (1 - 0) * exp(0) = 100.0
    assert report.scores.hygiene == 100.0
    # Churn has 0 hotspots -> S_churn = 100 * exp(0) = 100.0
    assert report.scores.churn == 100.0

    # SQLite persistence verification
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT overall_score, grade, report_data FROM repo_reports WHERE repo_name = 'org/perfect' ORDER BY rowid DESC LIMIT 1"
    )
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == report.scores.overall
    assert row[1] == report.scores.grade

    # Verify loaded JSON is valid ReportDataModel
    loaded_data = json.loads(row[2])
    assert loaded_data["metadata"]["repo_name"] == "org/perfect"
    conn.close()


def test_score_calculation_degraded_repo():
    # Mock services to represent a highly degraded repository (cycles, dead code, hotspots)
    mock_symbol = MagicMock()
    mock_symbol.symbol_count = 10
    # Let's say 5 of these are dead/unused (50% dead code ratio)
    mock_symbol.symbols = [
        MagicMock(name=f"func_{i}", type="function") for i in range(10)
    ]
    for i, s in enumerate(mock_symbol.symbols):
        s.name = f"func_{i}"

    mock_symbol_service = MagicMock()
    mock_symbol_service.load.return_value = mock_symbol

    mock_dead_code = MagicMock()
    mock_dead_code.unused_files = [
        MagicMock(file_path=f"file_{i}.py", recommendation="Clean") for i in range(5)
    ]
    mock_dead_code_service = MagicMock()
    mock_dead_code_service.analyze.return_value = mock_dead_code

    mock_churn = MagicMock()
    # 5 hotspots out of 10 files (50% hotspot ratio)
    mock_churn.hotspots = [
        MagicMock(file_path=f"file_{i}.py", churn_score=0.9) for i in range(5)
    ]
    mock_churn.file_records = [MagicMock() for _ in range(10)]
    mock_git_history_service = MagicMock()
    mock_git_history_service.load.return_value = mock_churn

    # Graph with circular dependency: a -> b -> a
    mock_graph = nx.DiGraph()
    mock_graph.add_edge("a.py", "b.py")
    mock_graph.add_edge("b.py", "a.py")

    mock_graph_service = MagicMock()
    mock_graph_service.load_graph.return_value = mock_graph

    mock_analysis = MagicMock()
    mock_analysis.metadata = {"loc": "1200", "commits_count": "45"}
    mock_analysis.tech_stack = ["python"]

    mock_architecture = MagicMock()
    mock_architecture.reading_order = []

    store = {
        "org/degraded": {"analysis": mock_analysis, "architecture": mock_architecture}
    }

    composer = ReportComposer(
        store=store,
        symbol_service=mock_symbol_service,
        call_graph_service=MagicMock(),
        dead_code_service=mock_dead_code_service,
        git_history_service=mock_git_history_service,
        graph_service=mock_graph_service,
    )

    report = composer.compose_report("org/degraded")

    assert isinstance(report, ReportDataModel)
    assert report.metadata.repo_name == "org/degraded"

    # Check that score is significantly degraded
    assert report.scores.overall < 80.0
    assert report.scores.architecture < 80.0
    assert report.scores.hygiene < 80.0
    assert report.scores.churn < 80.0
    assert report.scores.grade in ["B", "C", "D", "F"]
