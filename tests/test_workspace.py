"""Unit tests for the Intelligent IDE Workspace layer."""

import os
import sys
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from backend.api import app
from models.workspace import (
    AdvisorPanel,
    ExecutionPanel,
    FindingsPanel,
    OverviewPanel,
    WorkspaceSnapshot,
    WorkspaceState,
)
from services.workspace import (
    NavigationService,
    PanelComposer,
    WorkspaceCoordinator,
    WorkspaceService,
)

client = TestClient(app)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _twin(files=10, symbols=50, language="Python") -> Dict[str, Any]:
    return {
        "metadata": {"description": "Test repo", "stars": 42},
        "languages": {language: 90},
        "file_count": files,
        "symbol_count": symbols,
        "architecture_style": "layered",
        "dependency_count": 5,
        "indexed_at": 1000.0,
    }


def _kg(node_count=5, edge_count=8) -> Dict[str, Any]:
    nodes = [
        {"id": f"n{i}", "label": f"module_{i}", "kind": "module", "file_path": f"module_{i}.py"}
        for i in range(node_count)
    ]
    edges = [
        {"source": f"n{i}", "target": f"n{(i+1) % node_count}", "kind": "imports"}
        for i in range(edge_count)
    ]
    return {"nodes": nodes, "edges": edges}


def _inspection_report(findings=None) -> Dict[str, Any]:
    findings = findings or [
        {
            "id": "f1",
            "title": "High coupling",
            "category": "architecture",
            "severity": "high",
            "confidence": 0.85,
            "affected_entities": ["a.py"],
            "recommendations": ["Apply DI"],
            "estimated_effort": "1 day",
        }
    ]
    return {
        "findings": findings,
        "overall_score": 75.0,
        "generated_at": 2000.0,
        "statistics": {"critical": 0, "high": 1, "medium": 0, "low": 0},
    }


def _memory_context(snapshots=2) -> Dict[str, Any]:
    return {
        "snapshots": [
            {
                "id": f"snap-{i}",
                "timestamp": float(1000 + i * 100),
                "commit_hash": f"abc{i}",
                "summary": f"Snapshot {i}",
                "metrics": {"health_score": 80.0},
            }
            for i in range(snapshots)
        ],
        "trends": {"health_score": "stable"},
    }


def _monitoring_status() -> Dict[str, Any]:
    return {
        "status": "active",
        "last_run_at": 3000.0,
        "last_trigger": "indexing",
        "run_count": 5,
        "health_trend": "stable",
        "overall_health_score": 82.0,
    }


def _monitoring_history() -> List[Dict[str, Any]]:
    return [
        {"id": "run-1", "trigger": "push", "finding_counts": {"critical": 0, "high": 1}},
        {"id": "run-2", "trigger": "push", "finding_counts": {"critical": 1, "high": 0}},
    ]


def _advisor_report() -> Dict[str, Any]:
    return {
        "overall_priority": "high",
        "recommendations": [
            {
                "id": "r1",
                "title": "Fix security issue",
                "priority": "high",
                "category": "security",
                "estimated_effort": "Half day",
            }
        ],
        "roadmap": [
            {
                "phase": 1,
                "title": "Phase 1",
                "recommendations": [{"id": "r1"}],
                "estimated_total_effort": "Half day",
            }
        ],
    }


def _execution_plan() -> Dict[str, Any]:
    return {
        "critical_path": ["t1", "t2"],
        "rollback_points": ["t2"],
        "conflicts": [],
        "batches": [
            {
                "id": "b1",
                "order": 1,
                "title": "Batch 1",
                "tasks": [{"id": "t1"}, {"id": "t2"}],
                "parallel": False,
                "estimated_total_effort": "Half day",
            }
        ],
        "statistics": {
            "total_tasks": 2,
            "total_batches": 1,
            "total_conflicts": 0,
            "rollback_checkpoints": 1,
            "by_risk": {"critical": 0, "high": 1, "medium": 0, "low": 1},
        },
    }


def _mock_coordinator(
    twin=None,
    kg=None,
    inspection=None,
    memory=None,
    mon_status=None,
    mon_history=None,
    advisor=None,
    execution=None,
) -> WorkspaceCoordinator:
    coord = WorkspaceCoordinator()
    coord.get_twin = lambda repo: twin
    coord.get_knowledge_graph = lambda repo: kg
    coord.get_inspection_report = lambda repo: inspection
    coord.get_memory_context = lambda repo: memory
    coord.get_monitoring_status = lambda repo: mon_status
    coord.get_monitoring_history = lambda repo, limit=5: mon_history or []
    coord.get_advisor_report = lambda repo: advisor
    coord.get_execution_plan = lambda repo: execution
    return coord


# ---------------------------------------------------------------------------
# 1. WorkspaceCoordinator — safe reads
# ---------------------------------------------------------------------------


class TestWorkspaceCoordinator:
    def test_returns_none_when_no_twin_builder(self):
        coord = WorkspaceCoordinator()
        assert coord.get_twin("owner/repo") is None

    def test_returns_none_when_no_kg_builder(self):
        coord = WorkspaceCoordinator()
        assert coord.get_knowledge_graph("owner/repo") is None

    def test_returns_none_when_no_inspector(self):
        coord = WorkspaceCoordinator()
        assert coord.get_inspection_report("owner/repo") is None

    def test_returns_empty_list_when_no_monitoring(self):
        coord = WorkspaceCoordinator()
        assert coord.get_monitoring_history("owner/repo") == []

    def test_safe_read_does_not_raise_on_error(self):
        coord = WorkspaceCoordinator()
        result = coord._safe(lambda: (_ for _ in ()).throw(RuntimeError("boom")), default="fallback")
        assert result == "fallback"


# ---------------------------------------------------------------------------
# 2. Panel Composer
# ---------------------------------------------------------------------------


class TestPanelComposerOverview:
    def test_overview_with_twin_and_inspection(self):
        composer = PanelComposer()
        panel = composer.compose_overview("owner/repo", _twin(), _inspection_report())
        assert panel.repository == "owner/repo"
        assert panel.primary_language == "Python"
        assert panel.total_files == 10
        assert panel.total_symbols == 50
        assert panel.health.high_count == 1

    def test_overview_without_twin(self):
        composer = PanelComposer()
        panel = composer.compose_overview("owner/repo", None, None)
        assert panel.repository == "owner/repo"
        assert panel.total_files == 0

    def test_overview_health_counts_from_inspection(self):
        composer = PanelComposer()
        inspection = _inspection_report()
        inspection["statistics"] = {"critical": 2, "high": 3, "medium": 1, "low": 0}
        panel = composer.compose_overview("owner/repo", None, inspection)
        assert panel.health.critical_count == 2
        assert panel.health.high_count == 3


class TestPanelComposerExplorer:
    def test_explorer_with_kg(self):
        composer = PanelComposer()
        panel = composer.compose_explorer("owner/repo", _kg(node_count=5, edge_count=8))
        assert panel.total_nodes == 5
        assert panel.total_edges == 8
        assert len(panel.root_nodes) > 0

    def test_explorer_without_kg(self):
        composer = PanelComposer()
        panel = composer.compose_explorer("owner/repo", None)
        assert panel.total_nodes == 0
        assert panel.root_nodes == []

    def test_explorer_dependency_summary(self):
        composer = PanelComposer()
        panel = composer.compose_explorer("owner/repo", _kg())
        assert "imports" in panel.dependency_summary


class TestPanelComposerChat:
    def test_chat_with_populated_kg(self):
        composer = PanelComposer()
        panel = composer.compose_chat("owner/repo", _kg(node_count=10))
        assert panel.grounding_available is True
        assert panel.context_nodes == 10
        assert len(panel.suggested_questions) > 0

    def test_chat_without_kg(self):
        composer = PanelComposer()
        panel = composer.compose_chat("owner/repo", None)
        assert panel.grounding_available is False
        assert panel.context_nodes == 0


class TestPanelComposerFindings:
    def test_findings_with_inspection(self):
        composer = PanelComposer()
        panel = composer.compose_findings("owner/repo", _inspection_report())
        assert panel.total_findings == 1
        assert panel.findings[0].severity == "high"
        assert "high" in panel.by_severity

    def test_findings_without_inspection(self):
        composer = PanelComposer()
        panel = composer.compose_findings("owner/repo", None)
        assert panel.total_findings == 0
        assert panel.findings == []

    def test_findings_category_grouping(self):
        composer = PanelComposer()
        panel = composer.compose_findings("owner/repo", _inspection_report())
        assert "architecture" in panel.by_category


class TestPanelComposerTimeline:
    def test_timeline_with_memory(self):
        composer = PanelComposer()
        panel = composer.compose_timeline("owner/repo", _memory_context(snapshots=3))
        assert panel.snapshot_count == 3
        assert len(panel.timeline) == 3
        assert panel.trends == {"health_score": "stable"}

    def test_timeline_without_memory(self):
        composer = PanelComposer()
        panel = composer.compose_timeline("owner/repo", None)
        assert panel.snapshot_count == 0


class TestPanelComposerMonitor:
    def test_monitor_with_status_and_history(self):
        composer = PanelComposer()
        panel = composer.compose_monitor("owner/repo", _monitoring_status(), _monitoring_history())
        assert panel.status == "active"
        assert panel.run_count == 5
        assert panel.overall_health_score == 82.0
        # Run-2 has a critical finding → should appear as alert
        assert len(panel.alerts) >= 1

    def test_monitor_without_data(self):
        composer = PanelComposer()
        panel = composer.compose_monitor("owner/repo", None, [])
        assert panel.status == "unknown"

    def test_monitor_alerts_only_for_elevated_runs(self):
        composer = PanelComposer()
        history = [{"id": "r1", "trigger": "push", "finding_counts": {"critical": 0, "high": 0}}]
        panel = composer.compose_monitor("owner/repo", None, history)
        assert len(panel.alerts) == 0


class TestPanelComposerAdvisor:
    def test_advisor_with_report(self):
        composer = PanelComposer()
        panel = composer.compose_advisor("owner/repo", _advisor_report())
        assert panel.overall_priority == "high"
        assert panel.total_recommendations == 1
        assert len(panel.top_recommendations) == 1
        assert panel.roadmap_phases == 1

    def test_advisor_without_report(self):
        composer = PanelComposer()
        panel = composer.compose_advisor("owner/repo", None)
        assert panel.total_recommendations == 0


class TestPanelComposerExecution:
    def test_execution_with_plan(self):
        composer = PanelComposer()
        panel = composer.compose_execution("owner/repo", _execution_plan())
        assert panel.total_tasks == 2
        assert panel.total_batches == 1
        assert panel.critical_path_length == 2
        assert panel.rollback_checkpoints == 1
        assert panel.overall_risk == "high"

    def test_execution_without_plan(self):
        composer = PanelComposer()
        panel = composer.compose_execution("owner/repo", None)
        assert panel.total_tasks == 0
        assert panel.overall_risk == "low"

    def test_execution_batch_summaries(self):
        composer = PanelComposer()
        panel = composer.compose_execution("owner/repo", _execution_plan())
        assert len(panel.batches) == 1
        assert panel.batches[0].task_count == 2


# ---------------------------------------------------------------------------
# 3. Navigation Service
# ---------------------------------------------------------------------------


class TestNavigationService:
    def test_navigate_to_file_returns_matching_nodes(self):
        coord = _mock_coordinator(kg=_kg())
        svc = NavigationService(coord)
        result = svc.navigate_to_file("owner/repo", "module_0.py")
        assert "module_0.py" in result["file"]
        assert isinstance(result["nodes"], list)

    def test_navigate_to_symbol_returns_matching_nodes(self):
        coord = _mock_coordinator(kg=_kg())
        svc = NavigationService(coord)
        result = svc.navigate_to_symbol("owner/repo", "module_0")
        assert result["symbol"] == "module_0"
        assert isinstance(result["nodes"], list)

    def test_navigate_without_kg_returns_empty(self):
        coord = _mock_coordinator(kg=None)
        svc = NavigationService(coord)
        result = svc.navigate_to_file("owner/repo", "a.py")
        assert result["nodes"] == []

    def test_call_hierarchy_without_kg(self):
        coord = _mock_coordinator(kg=None)
        svc = NavigationService(coord)
        result = svc.get_call_hierarchy("owner/repo", "my_func")
        assert result["callers"] == []
        assert result["callees"] == []


# ---------------------------------------------------------------------------
# 4. WorkspaceService — full composition
# ---------------------------------------------------------------------------


class TestWorkspaceService:
    def test_get_workspace_returns_all_panels(self):
        coord = _mock_coordinator(
            twin=_twin(),
            kg=_kg(),
            inspection=_inspection_report(),
            memory=_memory_context(),
            mon_status=_monitoring_status(),
            mon_history=_monitoring_history(),
            advisor=_advisor_report(),
            execution=_execution_plan(),
        )
        svc = WorkspaceService(coord)
        snapshot = svc.get_workspace("owner/repo")
        assert isinstance(snapshot, WorkspaceSnapshot)
        assert snapshot.overview is not None
        assert snapshot.explorer is not None
        assert snapshot.chat is not None
        assert snapshot.findings is not None
        assert snapshot.timeline is not None
        assert snapshot.monitor is not None
        assert snapshot.advisor is not None
        assert snapshot.execution is not None

    def test_available_panels_reflects_populated_data(self):
        coord = _mock_coordinator(
            twin=_twin(),
            kg=_kg(),
            inspection=_inspection_report(),
            advisor=_advisor_report(),
        )
        svc = WorkspaceService(coord)
        snapshot = svc.get_workspace("owner/repo")
        assert "overview" in snapshot.available_panels
        assert "findings" in snapshot.available_panels
        assert "advisor" in snapshot.available_panels

    def test_available_panels_omits_empty_data(self):
        coord = _mock_coordinator(twin=_twin(), kg=_kg())
        svc = WorkspaceService(coord)
        snapshot = svc.get_workspace("owner/repo")
        assert "findings" not in snapshot.available_panels
        assert "advisor" not in snapshot.available_panels
        assert "execution" not in snapshot.available_panels

    def test_get_overview_panel(self):
        coord = _mock_coordinator(twin=_twin())
        svc = WorkspaceService(coord)
        panel = svc.get_overview("owner/repo")
        assert panel.total_files == 10

    def test_get_findings_panel(self):
        coord = _mock_coordinator(inspection=_inspection_report())
        svc = WorkspaceService(coord)
        panel = svc.get_findings("owner/repo")
        assert panel.total_findings == 1

    def test_get_monitor_panel(self):
        coord = _mock_coordinator(
            mon_status=_monitoring_status(),
            mon_history=_monitoring_history(),
        )
        svc = WorkspaceService(coord)
        panel = svc.get_monitor("owner/repo")
        assert panel.status == "active"

    def test_state_is_passed_through_to_snapshot(self):
        coord = _mock_coordinator(twin=_twin(), kg=_kg())
        svc = WorkspaceService(coord)
        state = WorkspaceState(
            repository="owner/repo",
            selected_file="main.py",
            active_panel="findings",
        )
        snapshot = svc.get_workspace("owner/repo", state=state)
        assert snapshot.state.selected_file == "main.py"
        assert snapshot.state.active_panel == "findings"


# ---------------------------------------------------------------------------
# 5. REST Endpoints
# ---------------------------------------------------------------------------


class TestWorkspaceRouter:
    def test_get_workspace_returns_404_for_unindexed_repo(self):
        response = client.get("/api/repositories/ghost/nonexistent/workspace")
        assert response.status_code == 404

    def test_get_overview_returns_404_for_unindexed_repo(self):
        response = client.get("/api/repositories/ghost/nonexistent/workspace/overview")
        assert response.status_code == 404

    def test_get_explorer_returns_404_for_unindexed_repo(self):
        response = client.get("/api/repositories/ghost/nonexistent/workspace/explorer")
        assert response.status_code == 404

    def test_get_chat_returns_404_for_unindexed_repo(self):
        response = client.get("/api/repositories/ghost/nonexistent/workspace/chat")
        assert response.status_code == 404

    def test_get_findings_returns_404_for_unindexed_repo(self):
        response = client.get("/api/repositories/ghost/nonexistent/workspace/findings")
        assert response.status_code == 404

    def test_get_timeline_returns_404_for_unindexed_repo(self):
        response = client.get("/api/repositories/ghost/nonexistent/workspace/timeline")
        assert response.status_code == 404

    def test_get_monitor_returns_404_for_unindexed_repo(self):
        response = client.get("/api/repositories/ghost/nonexistent/workspace/monitor")
        assert response.status_code == 404

    def test_get_advisor_returns_404_for_unindexed_repo(self):
        response = client.get("/api/repositories/ghost/nonexistent/workspace/advisor")
        assert response.status_code == 404

    def test_get_execution_returns_404_for_unindexed_repo(self):
        response = client.get("/api/repositories/ghost/nonexistent/workspace/execution")
        assert response.status_code == 404

    def test_get_workspace_returns_snapshot_when_mocked(self):
        coord = _mock_coordinator(twin=_twin(), kg=_kg(), inspection=_inspection_report())
        svc = WorkspaceService(coord)
        snapshot = svc.get_workspace("owner/repo")
        with patch("backend.routers.workspace.workspace_service") as mock_svc:
            mock_svc.get_workspace.return_value = snapshot
            with patch("backend.routers.workspace.repository_twin_builder") as mock_twin:
                mock_twin.build_twin.return_value = MagicMock()
                response = client.get("/api/repositories/owner/repo/workspace")
                assert response.status_code == 200
                data = response.json()
                assert "state" in data
                assert "overview" in data
                assert "explorer" in data
                assert "available_panels" in data

    def test_get_overview_returns_panel_when_mocked(self):
        panel = OverviewPanel(repository="owner/repo", total_files=10)
        with patch("backend.routers.workspace.workspace_service") as mock_svc:
            mock_svc.get_overview.return_value = panel
            with patch("backend.routers.workspace.repository_twin_builder") as mock_twin:
                mock_twin.build_twin.return_value = MagicMock()
                response = client.get("/api/repositories/owner/repo/workspace/overview")
                assert response.status_code == 200
                data = response.json()
                assert data["repository"] == "owner/repo"
                assert data["total_files"] == 10

    def test_get_findings_returns_panel_when_mocked(self):
        panel = FindingsPanel(repository="owner/repo", total_findings=2)
        with patch("backend.routers.workspace.workspace_service") as mock_svc:
            mock_svc.get_findings.return_value = panel
            with patch("backend.routers.workspace.repository_twin_builder") as mock_twin:
                mock_twin.build_twin.return_value = MagicMock()
                response = client.get("/api/repositories/owner/repo/workspace/findings")
                assert response.status_code == 200
                assert response.json()["total_findings"] == 2

    def test_get_advisor_returns_panel_when_mocked(self):
        panel = AdvisorPanel(repository="owner/repo", overall_priority="high", total_recommendations=3)
        with patch("backend.routers.workspace.workspace_service") as mock_svc:
            mock_svc.get_advisor.return_value = panel
            with patch("backend.routers.workspace.repository_twin_builder") as mock_twin:
                mock_twin.build_twin.return_value = MagicMock()
                response = client.get("/api/repositories/owner/repo/workspace/advisor")
                assert response.status_code == 200
                data = response.json()
                assert data["overall_priority"] == "high"
                assert data["total_recommendations"] == 3

    def test_get_execution_returns_panel_when_mocked(self):
        panel = ExecutionPanel(repository="owner/repo", total_tasks=5, overall_risk="medium")
        with patch("backend.routers.workspace.workspace_service") as mock_svc:
            mock_svc.get_execution.return_value = panel
            with patch("backend.routers.workspace.repository_twin_builder") as mock_twin:
                mock_twin.build_twin.return_value = MagicMock()
                response = client.get("/api/repositories/owner/repo/workspace/execution")
                assert response.status_code == 200
                data = response.json()
                assert data["total_tasks"] == 5
                assert data["overall_risk"] == "medium"
