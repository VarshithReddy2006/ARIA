"""Regression tests for the Repository Intelligence Pipeline (v1.0.0-rc1).

Verifies the fixes to all 7 inspection packs, advisor roadmap, execution planner,
and associated FastAPI routes.
"""

import sys
import os
from unittest.mock import patch
from fastapi.testclient import TestClient

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.api import app
from models.inspection import Finding, InspectionContext
from models.advisor import AdvisorRecommendation, AdvisorReport
from models.execution import ExecutionPlan
from models.workspace import FindingsPanel, AdvisorPanel, ExecutionPanel
from services.inspection import (
    ArchitectureInspector,
    SecurityInspector,
    DependencyInspector,
    DeadCodeInspector,
    DocumentationInspector,
    ComplexityInspector,
    PerformanceInspector,
)
from services.advisor import AdvisorService
from services.execution_planner import ExecutionPlannerService

client = TestClient(app)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_context(twin_overrides=None, kg_overrides=None) -> InspectionContext:
    return InspectionContext(
        repository="owner/repo",
        twin={
            "repository_name": "owner/repo",
            "files": ["main.py", "utils.py", "README.md"],
            "metadata": {"local_path": "/mock/repo"},
            "symbols_summary": {},
            "dependencies_summary": {},
            "architecture_summary": {},
            "health_summary": {},
            "compliance_summary": {},
            **(twin_overrides or {}),
        },
        knowledge_graph={
            "nodes": [],
            "edges": [],
            **(kg_overrides or {}),
        },
    )


# ---------------------------------------------------------------------------
# 1. Inspector Pack Tests
# ---------------------------------------------------------------------------


class TestInspectorPacksRegression:
    def test_architecture_inspector_resolves_from_kg(self):
        ctx = _mock_context(
            kg_overrides={
                "edges": [
                    {
                        "source": "owner/repo::main.py",
                        "target": "owner/repo::utils.py",
                        "type": "IMPORTS",
                    }
                ]
            }
        )
        findings = ArchitectureInspector().inspect(ctx)
        # Should complete successfully without raising errors
        assert isinstance(findings, list)

    def test_security_inspector_resolves_from_compliance_summary(self):
        ctx = _mock_context(
            twin_overrides={
                "compliance_summary": {
                    "status": "warning",
                    "reasons": ["Possible secret token exposed in config file."],
                    "has_license": True,
                    "cycles_count": 0,
                    "dead_code_ratio": 0.0,
                }
            }
        )
        findings = SecurityInspector().inspect(ctx)
        assert len(findings) > 0
        assert findings[0].category == "security"

    def test_dependency_inspector_resolves_from_kg(self):
        ctx = _mock_context(
            kg_overrides={
                "edges": [
                    {
                        "source": "owner/repo::main.py",
                        "target": "owner/repo::utils.py",
                        "type": "IMPORTS",
                    },
                    {
                        "source": "owner/repo::utils.py",
                        "target": "owner/repo::main.py",
                        "type": "IMPORTS",
                    },
                ]
            }
        )
        findings = DependencyInspector().inspect(ctx)
        assert len(findings) > 0
        assert findings[0].category == "dependency"

    def test_dead_code_inspector_resolves_from_compliance_summary(self):
        ctx = _mock_context(
            twin_overrides={
                "compliance_summary": {
                    "status": "warning",
                    "reasons": ["Dead code ratio is high (>15%)."],
                    "has_license": True,
                    "cycles_count": 0,
                    "dead_code_ratio": 16.0,
                }
            }
        )
        findings = DeadCodeInspector().inspect(ctx)
        assert len(findings) > 0
        assert findings[0].category == "dead_code"

    def test_documentation_inspector_resolves_from_kg(self):
        ctx = _mock_context(
            kg_overrides={
                "nodes": [
                    {
                        "id": "owner/repo::main.py::foo",
                        "type": "symbol",
                        "properties": {"name": "foo"},
                    }
                ]
            }
        )
        findings = DocumentationInspector().inspect(ctx)
        assert len(findings) > 0
        assert findings[0].category == "documentation"

    def test_complexity_inspector_resolves_from_kg(self):
        ctx = _mock_context(
            kg_overrides={
                "nodes": [
                    {
                        "id": "owner/repo::main.py::bar",
                        "type": "symbol",
                        "properties": {"name": "bar"},
                    }
                ],
                "edges": [
                    {
                        "source": "owner/repo::main.py::bar",
                        "target": "owner/repo::main.py::foo",
                        "type": "CALLS",
                    },
                    {
                        "source": "owner/repo::main.py::bar",
                        "target": "owner/repo::main.py::baz",
                        "type": "CALLS",
                    },
                    {
                        "source": "owner/repo::main.py::bar",
                        "target": "owner/repo::main.py::qux",
                        "type": "CALLS",
                    },
                    {
                        "source": "owner/repo::main.py::bar",
                        "target": "owner/repo::main.py::xyz",
                        "type": "CALLS",
                    },
                ],
            }
        )
        findings = ComplexityInspector().inspect(ctx)
        assert len(findings) > 0
        assert findings[0].category == "complexity"

    def test_performance_inspector_handles_dicts_gracefully(self):
        ctx = _mock_context(
            twin_overrides={"files": [{"path": "big_file.py", "size": 120000}]}
        )
        findings = PerformanceInspector().inspect(ctx)
        assert len(findings) > 0
        assert findings[0].category == "performance"


# ---------------------------------------------------------------------------
# 2. Advisor Service Tests
# ---------------------------------------------------------------------------


class TestAdvisorServiceRegression:
    def test_advisor_aggregates_findings_correctly(self):
        service = AdvisorService()
        mock_finding = Finding(
            id="f-1",
            category="security",
            severity="critical",
            confidence=0.9,
            title="Vulnerability",
            description="Exposed token.",
            recommendations=["Revoke it."],
            estimated_effort="1 hour",
        )
        report = {
            "repository": "owner/repo",
            "findings": [mock_finding.model_dump()],
        }
        with patch.object(service, "_save") as _mock_save:
            adv_report = service.advise("owner/repo", inspection_report=report)
            assert isinstance(adv_report, AdvisorReport)
            assert len(adv_report.recommendations) > 0
            assert adv_report.recommendations[0].priority == "critical"
            assert len(adv_report.roadmap) > 0


# ---------------------------------------------------------------------------
# 3. Execution Planner Tests
# ---------------------------------------------------------------------------


class TestExecutionPlannerRegression:
    def test_execution_planner_decomposes_recommendations(self):
        service = ExecutionPlannerService()
        mock_rec = AdvisorRecommendation(
            id="r-1",
            title="Fix Security",
            description="Remediate vuln.",
            category="security",
            priority="critical",
            estimated_effort="2 hours",
            confidence=0.9,
            sources=["RepositoryInspector"],
        )
        report = {
            "repository": "owner/repo",
            "recommendations": [mock_rec.model_dump()],
        }
        with patch.object(service, "_save") as _mock_save:
            plan = service.plan("owner/repo", advisor_report=report)
            assert isinstance(plan, ExecutionPlan)
            assert len(plan.batches) > 0
            assert len(plan.critical_path) > 0
            assert len(plan.rollback_points) > 0


# ---------------------------------------------------------------------------
# 4. REST API Route Tests
# ---------------------------------------------------------------------------


class TestRESTAPIRoutesRegression:
    @patch("backend.routers.workspace.repository_twin_builder")
    @patch("backend.routers.workspace.workspace_service")
    def test_workspace_findings_endpoint(self, mock_service, _mock_builder):
        mock_service.get_findings.return_value = FindingsPanel(
            repository="owner/repo",
            total_findings=0,
            findings=[],
            by_severity={},
            by_category={},
        )
        response = client.get("/api/repositories/owner/repo/workspace/findings")
        assert response.status_code == 200
        assert response.json()["repository"] == "owner/repo"

    @patch("backend.routers.workspace.repository_twin_builder")
    @patch("backend.routers.workspace.workspace_service")
    def test_workspace_advisor_endpoint(self, mock_service, _mock_builder):
        mock_service.get_advisor.return_value = AdvisorPanel(
            repository="owner/repo",
            overall_priority="low",
            total_recommendations=0,
            top_recommendations=[],
            roadmap_phases=0,
            roadmap_summary=[],
        )
        response = client.get("/api/repositories/owner/repo/workspace/advisor")
        assert response.status_code == 200
        assert response.json()["repository"] == "owner/repo"

    @patch("backend.routers.workspace.repository_twin_builder")
    @patch("backend.routers.workspace.workspace_service")
    def test_workspace_execution_endpoint(self, mock_service, _mock_builder):
        mock_service.get_execution.return_value = ExecutionPanel(
            repository="owner/repo",
            total_tasks=0,
            total_batches=0,
            critical_path_length=0,
            rollback_checkpoints=0,
            conflict_count=0,
            overall_risk="low",
            batches=[],
            critical_path=[],
        )
        response = client.get("/api/repositories/owner/repo/workspace/execution")
        assert response.status_code == 200
        assert response.json()["repository"] == "owner/repo"
