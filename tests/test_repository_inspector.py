"""Unit tests for the Autonomous Repository Inspector (ARI)."""

import sys
import os
import tempfile
from unittest.mock import patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from backend.api import app

from models.inspection import Finding, InspectionContext, InspectionReport
from services.inspection import (
    ArchitectureInspector,
    ComplexityInspector,
    DependencyInspector,
    DocumentationInspector,
    SecurityInspector,
    TestingInspector,
)
from services.repository_inspector import (
    ConfidenceEngine,
    FindingAggregator,
    InspectionPlanner,
    RecommendationPlanner,
    RepositoryInspector,
    SeverityEngine,
)

client = TestClient(app)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _minimal_context(files=None, twin_overrides=None, kg_overrides=None) -> InspectionContext:
    files = files or ["src/main.py", "src/utils.py"]
    return InspectionContext(
        repository="owner/repo",
        twin={
            "files": files,
            "metadata": {"health_score": 80.0, "complexity": 2.0, "total_loc": 1000},
            "architecture": {"relationships": []},
            "dependencies": {"relationships": []},
            "compliance": {"vulnerabilities": [], "warnings": []},
            "symbols": {"declarations": []},
            **(twin_overrides or {}),
        },
        knowledge_graph={"nodes": [], "edges": [], **(kg_overrides or {})},
    )


def _finding(
    category="architecture",
    severity="medium",
    confidence=0.8,
    title="A Finding",
    estimated_effort="2 hours",
    evidence=None,
) -> Finding:
    return Finding(
        id="test-id",
        category=category,
        severity=severity,
        confidence=confidence,
        title=title,
        description="Test description.",
        estimated_effort=estimated_effort,
        evidence=evidence or [],
    )


# ---------------------------------------------------------------------------
# 1. Inspection Planner
# ---------------------------------------------------------------------------

class TestInspectionPlanner:
    def test_default_runs_all_packs(self):
        planner = InspectionPlanner()
        packs = planner.plan("default")
        assert len(packs) == 8

    def test_architecture_policy(self):
        planner = InspectionPlanner()
        packs = planner.plan("architecture")
        names = {type(p).__name__ for p in packs}
        assert "ArchitectureInspector" in names
        assert "DependencyInspector" in names
        assert "ComplexityInspector" in names
        assert "SecurityInspector" not in names
        assert "TestingInspector" not in names

    def test_security_policy(self):
        planner = InspectionPlanner()
        packs = planner.plan("security")
        names = {type(p).__name__ for p in packs}
        assert "SecurityInspector" in names
        assert "DependencyInspector" in names
        assert len(packs) == 2

    def test_unknown_policy_defaults_to_all(self):
        planner = InspectionPlanner()
        packs = planner.plan("nonexistent_policy")
        assert len(packs) == 8


# ---------------------------------------------------------------------------
# 2. Individual Inspection Packs
# ---------------------------------------------------------------------------

class TestInspectionPacks:
    def test_architecture_inspector_flags_cycles(self):
        ctx = _minimal_context(twin_overrides={
            "architecture": {
                "relationships": [
                    {"source": "ModA", "target": "ModB", "dependencies": ["x", "y", "z", "a", "b", "c", "d", "e", "f", "g", "k"]},
                    {"source": "ModB", "target": "ModA", "dependencies": []},
                ]
            }
        })
        findings = ArchitectureInspector().inspect(ctx)
        assert any(f.severity == "critical" for f in findings)
        assert any("Circular" in f.title for f in findings)

    def test_security_inspector_flags_vulnerabilities(self):
        ctx = _minimal_context(twin_overrides={
            "compliance": {
                "vulnerabilities": [{"affected_package": "requests", "version": "2.0", "cve": "CVE-2021-9999"}],
                "warnings": [],
            }
        })
        findings = SecurityInspector().inspect(ctx)
        assert any(f.category == "security" and f.severity == "critical" for f in findings)

    def test_security_inspector_flags_secrets(self):
        ctx = _minimal_context(twin_overrides={
            "compliance": {
                "vulnerabilities": [],
                "warnings": ["Hardcoded secret token found in config.py"],
            }
        })
        findings = SecurityInspector().inspect(ctx)
        assert any("Credentials" in f.title for f in findings)

    def test_dependency_inspector_flags_cycles(self):
        ctx = _minimal_context(twin_overrides={
            "dependencies": {
                "relationships": [
                    {"source": "a.py", "target": "b.py"},
                    {"source": "b.py", "target": "a.py"},
                ]
            }
        })
        findings = DependencyInspector().inspect(ctx)
        assert any("Circular" in f.title for f in findings)

    def test_complexity_inspector_flags_high_complexity(self):
        ctx = _minimal_context(twin_overrides={
            "metadata": {"health_score": 80.0, "complexity": 6.5, "total_loc": 1000}
        })
        findings = ComplexityInspector().inspect(ctx)
        assert any(f.category == "complexity" for f in findings)

    def test_documentation_inspector_flags_no_readme(self):
        ctx = _minimal_context(files=["src/main.py", "src/utils.py"])
        findings = DocumentationInspector().inspect(ctx)
        assert any("README" in f.title for f in findings)

    def test_documentation_inspector_passes_with_readme(self):
        ctx = _minimal_context(files=["readme.md", "src/main.py"])
        findings = DocumentationInspector().inspect(ctx)
        assert not any("README" in f.title for f in findings)

    def test_testing_inspector_flags_missing_tests(self):
        ctx = _minimal_context(files=["src/main.py", "src/utils.py"])
        findings = TestingInspector().inspect(ctx)
        assert any(f.category == "testing" and f.severity == "high" for f in findings)

    def test_testing_inspector_passes_with_tests(self):
        ctx = _minimal_context(files=["src/main.py", "tests/test_main.py"])
        findings = TestingInspector().inspect(ctx)
        assert not any(f.severity == "high" for f in findings)


# ---------------------------------------------------------------------------
# 3. Finding Aggregator
# ---------------------------------------------------------------------------

class TestFindingAggregator:
    def test_merges_similar_titles(self):
        agg = FindingAggregator()
        f1 = _finding(title="Circular dependency detected", evidence=["a -> b -> a"])
        f2 = _finding(title="Circular dependency exists", evidence=["b -> c -> b"])
        f3 = _finding(title="Dependency cycle found", evidence=["c -> d -> c"])
        merged = agg.aggregate([f1, f2, f3])
        # All three are similar enough to merge
        assert len(merged) <= 2

    def test_keeps_dissimilar_findings_separate(self):
        agg = FindingAggregator()
        f1 = _finding(category="architecture", title="High Component Coupling")
        f2 = _finding(category="security", title="Vulnerable Package Detected")
        merged = agg.aggregate([f1, f2])
        assert len(merged) == 2

    def test_escalates_severity_on_merge(self):
        agg = FindingAggregator()
        f1 = _finding(title="Circular dependency detected", severity="medium")
        f2 = _finding(title="Circular dependency exists", severity="high")
        merged = agg.aggregate([f1, f2])
        assert merged[0].severity == "high"

    def test_merges_evidence(self):
        agg = FindingAggregator()
        f1 = _finding(title="Circular dependency detected")
        f1.evidence = ["a -> b"]
        f2 = _finding(title="Circular dependency found")
        f2.evidence = ["b -> c"]
        merged = agg.aggregate([f1, f2])
        assert "a -> b" in merged[0].evidence
        assert "b -> c" in merged[0].evidence


# ---------------------------------------------------------------------------
# 4. Severity Engine
# ---------------------------------------------------------------------------

class TestSeverityEngine:
    def test_escalates_on_low_health(self):
        engine = SeverityEngine()
        finding = _finding(severity="medium")
        rescored = engine.rescore([finding], {"metadata": {"health_score": 40.0, "complexity": 1.0, "dependency_count": 0}})
        assert rescored[0].severity == "high"

    def test_no_escalation_on_healthy_repo(self):
        engine = SeverityEngine()
        finding = _finding(severity="low")
        rescored = engine.rescore([finding], {"metadata": {"health_score": 90.0, "complexity": 1.0, "dependency_count": 0}})
        assert rescored[0].severity == "low"


# ---------------------------------------------------------------------------
# 5. Confidence Engine
# ---------------------------------------------------------------------------

class TestConfidenceEngine:
    def test_boosts_confidence_with_more_evidence(self):
        engine = ConfidenceEngine()
        finding = _finding(confidence=0.7)
        finding.evidence = ["a", "b", "c"]
        rescored = engine.rescore([finding], {"metadata": {"symbols_count": 10, "files_count": 5}})
        assert rescored[0].confidence > 0.7

    def test_penalizes_no_entities_for_large_repo(self):
        engine = ConfidenceEngine()
        finding = _finding(confidence=0.9)
        finding.affected_entities = []
        rescored = engine.rescore([finding], {"metadata": {"symbols_count": 100, "files_count": 50}})
        assert rescored[0].confidence < 0.9


# ---------------------------------------------------------------------------
# 6. Recommendation Planner
# ---------------------------------------------------------------------------

class TestRecommendationPlanner:
    def test_fills_empty_recommendations(self):
        planner = RecommendationPlanner()
        finding = _finding(category="testing")
        finding.recommendations = []
        finding.estimated_effort = ""
        enriched = planner.enrich([finding])
        assert len(enriched[0].recommendations) > 0

    def test_does_not_overwrite_existing_recommendations(self):
        planner = RecommendationPlanner()
        finding = _finding(category="security")
        finding.recommendations = ["Custom remediation step."]
        enriched = planner.enrich([finding])
        assert "Custom remediation step." in enriched[0].recommendations


# ---------------------------------------------------------------------------
# 7. Full Report Generation
# ---------------------------------------------------------------------------

class TestRepositoryInspector:
    def test_full_inspection_produces_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            inspector = RepositoryInspector(base_dir=tmpdir)
            ctx = _minimal_context()
            report = inspector.inspect(
                repo_name="owner/repo",
                twin_data=ctx.twin,
                knowledge_graph_data=ctx.knowledge_graph,
                policy="default",
            )
            assert isinstance(report, InspectionReport)
            assert report.repository == "owner/repo"
            assert 0.0 <= report.overall_score <= 100.0
            assert isinstance(report.statistics, dict)
            assert "total_findings" in report.statistics
            assert "policy" in report.inspection_metadata

    def test_report_persisted_and_loaded(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            inspector = RepositoryInspector(base_dir=tmpdir)
            ctx = _minimal_context()
            report = inspector.inspect(
                repo_name="owner/repo",
                twin_data=ctx.twin,
                knowledge_graph_data=ctx.knowledge_graph,
                policy="default",
            )
            loaded = inspector.load_latest("owner/repo")
            assert loaded is not None
            assert loaded.repository == report.repository
            assert loaded.timestamp == report.timestamp

    def test_architecture_policy_restricts_packs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            inspector = RepositoryInspector(base_dir=tmpdir)
            ctx = _minimal_context()
            report = inspector.inspect(
                repo_name="owner/repo",
                twin_data=ctx.twin,
                knowledge_graph_data=ctx.knowledge_graph,
                policy="architecture",
            )
            packs_run = report.inspection_metadata.get("packs_run", [])
            assert "ArchitectureInspector" in packs_run
            assert "SecurityInspector" not in packs_run


# ---------------------------------------------------------------------------
# 8. REST Endpoints
# ---------------------------------------------------------------------------

class TestInspectionRouter:
    def test_post_inspect_returns_404_for_unindexed_repo(self):
        response = client.post("/api/repositories/ghost/nonexistent/inspect")
        assert response.status_code == 404

    def test_get_latest_returns_404_when_no_report(self):
        response = client.get("/api/repositories/ghost/nonexistent/inspection/latest")
        assert response.status_code == 404

    def test_get_findings_returns_404_when_no_report(self):
        response = client.get("/api/repositories/ghost/nonexistent/inspection/findings")
        assert response.status_code == 404

    def test_get_statistics_returns_404_when_no_report(self):
        response = client.get("/api/repositories/ghost/nonexistent/inspection/statistics")
        assert response.status_code == 404

    def test_get_latest_returns_report_when_cached(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("backend.routers.inspection.repository_inspector") as mock_inspector:
                mock_report = InspectionReport(
                    repository="owner/repo",
                    timestamp=1000.0,
                    overall_score=88.0,
                    findings=[],
                    statistics={"total_findings": 0},
                    summary={},
                    inspection_metadata={"policy": "default"},
                )
                mock_inspector.load_latest.return_value = mock_report
                response = client.get("/api/repositories/owner/repo/inspection/latest")
                assert response.status_code == 200
                data = response.json()
                assert data["overall_score"] == 88.0
                assert data["repository"] == "owner/repo"
