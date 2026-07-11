"""Unit tests for the AI Engineering Advisor (AEA) pipeline."""

import os
import sys
import tempfile
import uuid
from typing import Any, Dict, List, Optional
from unittest.mock import patch


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from backend.api import app
from models.advisor import AdvisorRecommendation, AdvisorReport
from services.advisor import (
    AdvisorService,
    DuplicateResolver,
    EffortEstimator,
    PriorityEngine,
    RecommendationAggregator,
    RoadmapPlanner,
)

client = TestClient(app)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rec(
    title="Fix security vulnerability",
    category="security",
    priority="high",
    confidence=0.9,
    effort="unknown",
    sources=None,
    entities=None,
    evidence=None,
    recurrence=1,
) -> AdvisorRecommendation:
    return AdvisorRecommendation(
        id=str(uuid.uuid4()),
        title=title,
        description="Test description.",
        category=category,
        priority=priority,
        estimated_effort=effort,
        confidence=confidence,
        sources=sources or ["RepositoryInspector"],
        affected_entities=entities or [],
        evidence=evidence or [],
        recurrence_count=recurrence,
    )


def _inspection_report(
    findings: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    findings = findings or [
        {
            "id": "f1",
            "title": "High Coupling",
            "description": "Module A is too coupled.",
            "category": "architecture",
            "severity": "high",
            "confidence": 0.85,
            "estimated_effort": "1 day",
            "recommendations": ["Reduce coupling by applying dependency inversion."],
            "affected_entities": ["module_a.py"],
            "evidence": ["A depends on B, C, D"],
        }
    ]
    return {"findings": findings, "overall_score": 78.0}


def _reasoning_result() -> Dict[str, Any]:
    return {
        "recommendations": [
            {
                "title": "Adopt dependency injection",
                "rationale": "Reduces tight coupling between modules.",
                "category": "architecture",
                "priority": "medium",
                "estimated_effort": "2–3 days",
                "confidence": 0.8,
                "related_entities": ["module_a.py"],
                "evidence_ids": ["e1", "e2"],
            }
        ]
    }


def _memory_context_degrading() -> Dict[str, Any]:
    return {
        "trends": [
            {
                "metric": "health_score",
                "direction": "degrading",
                "window": 3,
                "confidence": 0.75,
            }
        ]
    }


def _monitoring_run_critical() -> Dict[str, Any]:
    return {
        "id": "run-1",
        "trigger": "indexing",
        "finding_counts": {"critical": 2, "high": 1},
    }


# ---------------------------------------------------------------------------
# 1. Recommendation Aggregator
# ---------------------------------------------------------------------------


class TestRecommendationAggregator:
    def test_aggregates_from_inspection_report(self):
        agg = RecommendationAggregator()
        recs = agg.from_inspection_report(_inspection_report())
        assert len(recs) > 0
        assert all(r.sources == ["RepositoryInspector"] for r in recs)
        assert all(r.category == "architecture" for r in recs)

    def test_aggregates_from_reasoning_result(self):
        agg = RecommendationAggregator()
        recs = agg.from_reasoning_result(_reasoning_result())
        assert len(recs) == 1
        assert recs[0].sources == ["EngineeringReasoningEngine"]

    def test_aggregates_from_degrading_memory(self):
        agg = RecommendationAggregator()
        recs = agg.from_memory_context(_memory_context_degrading())
        assert len(recs) == 1
        assert recs[0].sources == ["EngineeringMemory"]
        assert recs[0].priority == "high"

    def test_skips_stable_memory_trends(self):
        agg = RecommendationAggregator()
        recs = agg.from_memory_context(
            {"trends": [{"metric": "health_score", "direction": "stable", "window": 3}]}
        )
        assert len(recs) == 0

    def test_aggregates_critical_from_monitoring(self):
        agg = RecommendationAggregator()
        recs = agg.from_monitoring_run(_monitoring_run_critical())
        assert len(recs) == 1
        assert recs[0].priority == "critical"
        assert recs[0].sources == ["ContinuousMonitoring"]

    def test_aggregates_high_severity_monitoring(self):
        agg = RecommendationAggregator()
        recs = agg.from_monitoring_run(
            {
                "id": "r1",
                "trigger": "push",
                "finding_counts": {"critical": 0, "high": 3},
            }
        )
        assert len(recs) == 1
        assert recs[0].priority == "high"

    def test_no_monitoring_rec_when_no_findings(self):
        agg = RecommendationAggregator()
        recs = agg.from_monitoring_run(
            {"id": "r1", "trigger": "push", "finding_counts": {}}
        )
        assert len(recs) == 0

    def test_skips_ungrounded_rag_recommendations(self):
        agg = RecommendationAggregator()
        recs = agg.from_graph_rag_result(
            {
                "grounded": False,
                "recommendations": [{"title": "Bad rec", "description": ""}],
            }
        )
        assert len(recs) == 0

    def test_aggregate_combines_all_sources(self):
        agg = RecommendationAggregator()
        all_recs = agg.aggregate(
            inspection_report=_inspection_report(),
            reasoning_result=_reasoning_result(),
            memory_context=_memory_context_degrading(),
            monitoring_run=_monitoring_run_critical(),
        )
        sources = {src for r in all_recs for src in r.sources}
        assert "RepositoryInspector" in sources
        assert "EngineeringReasoningEngine" in sources
        assert "EngineeringMemory" in sources
        assert "ContinuousMonitoring" in sources

    def test_aggregate_with_no_sources_returns_empty(self):
        agg = RecommendationAggregator()
        assert agg.aggregate() == []


# ---------------------------------------------------------------------------
# 2. Duplicate Resolver
# ---------------------------------------------------------------------------


class TestDuplicateResolver:
    def test_merges_highly_similar_titles(self):
        resolver = DuplicateResolver()
        r1 = _rec(title="Fix security vulnerability in module A")
        r2 = _rec(title="Fix security vulnerability in module A")
        merged = resolver.resolve([r1, r2])
        assert len(merged) == 1

    def test_keeps_dissimilar_titles(self):
        resolver = DuplicateResolver()
        r1 = _rec(title="Fix security CVE", category="security")
        r2 = _rec(title="Refactor architecture", category="architecture")
        merged = resolver.resolve([r1, r2])
        assert len(merged) == 2

    def test_merges_same_category_and_overlapping_entities(self):
        resolver = DuplicateResolver()
        r1 = _rec(
            title="High coupling", category="architecture", entities=["a.py", "b.py"]
        )
        r2 = _rec(
            title="Tight coupling", category="architecture", entities=["a.py", "c.py"]
        )
        merged = resolver.resolve([r1, r2])
        assert len(merged) == 1

    def test_escalates_priority_on_merge(self):
        resolver = DuplicateResolver()
        r1 = _rec(title="Security issue", category="security", priority="medium")
        r2 = _rec(title="Security issue", category="security", priority="critical")
        merged = resolver.resolve([r1, r2])
        assert merged[0].priority == "critical"

    def test_preserves_all_sources_on_merge(self):
        resolver = DuplicateResolver()
        r1 = _rec(title="Security issue", sources=["RepositoryInspector"])
        r2 = _rec(title="Security issue", sources=["ContinuousMonitoring"])
        merged = resolver.resolve([r1, r2])
        assert "RepositoryInspector" in merged[0].sources
        assert "ContinuousMonitoring" in merged[0].sources

    def test_preserves_all_evidence_on_merge(self):
        resolver = DuplicateResolver()
        r1 = _rec(title="Security issue", evidence=["CVE-2021-1"])
        r2 = _rec(title="Security issue", evidence=["CVE-2021-2"])
        merged = resolver.resolve([r1, r2])
        assert "CVE-2021-1" in merged[0].evidence
        assert "CVE-2021-2" in merged[0].evidence

    def test_accumulates_recurrence_count(self):
        resolver = DuplicateResolver()
        r1 = _rec(title="Security issue", recurrence=2)
        r2 = _rec(title="Security issue", recurrence=3)
        merged = resolver.resolve([r1, r2])
        assert merged[0].recurrence_count == 5

    def test_takes_max_confidence(self):
        resolver = DuplicateResolver()
        r1 = _rec(title="Security issue", confidence=0.6)
        r2 = _rec(title="Security issue", confidence=0.9)
        merged = resolver.resolve([r1, r2])
        assert merged[0].confidence == 0.9


# ---------------------------------------------------------------------------
# 3. Priority Engine
# ---------------------------------------------------------------------------


class TestPriorityEngine:
    def test_security_critical_stays_critical(self):
        engine = PriorityEngine()
        rec = _rec(category="security", priority="critical", confidence=1.0)
        result = engine.prioritize([rec])
        assert result[0].priority == "critical"

    def test_lower_severity_with_high_recurrence_escalates(self):
        engine = PriorityEngine()
        rec = _rec(category="security", priority="low", confidence=1.0, recurrence=10)
        result = engine.prioritize([rec])
        # Recurrence bonus should push score into high range
        assert result[0].priority in ("high", "critical")

    def test_sorted_by_priority_descending(self):
        engine = PriorityEngine()
        recs = [
            _rec(
                title="Low thing",
                category="documentation",
                priority="low",
                confidence=0.5,
            ),
            _rec(
                title="Critical thing",
                category="security",
                priority="critical",
                confidence=1.0,
            ),
            _rec(
                title="Medium thing",
                category="architecture",
                priority="medium",
                confidence=0.8,
            ),
        ]
        result = engine.prioritize(recs)
        scores = [r.metadata.get("priority_score", 0) for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_stores_priority_score_in_metadata(self):
        engine = PriorityEngine()
        rec = _rec(category="security", priority="high", confidence=0.9)
        result = engine.prioritize([rec])
        assert "priority_score" in result[0].metadata
        assert result[0].metadata["priority_score"] > 0


# ---------------------------------------------------------------------------
# 4. Effort Estimator
# ---------------------------------------------------------------------------


class TestEffortEstimator:
    def test_fills_unknown_effort(self):
        estimator = EffortEstimator()
        rec = _rec(category="architecture", effort="unknown")
        result = estimator.estimate([rec])
        assert result[0].estimated_effort != "unknown"
        assert result[0].estimated_effort != ""

    def test_does_not_overwrite_known_effort(self):
        estimator = EffortEstimator()
        rec = _rec(category="security", effort="< 2 hours")
        result = estimator.estimate([rec])
        assert result[0].estimated_effort == "< 2 hours"

    def test_more_entities_increases_effort(self):
        estimator = EffortEstimator()
        rec_small = _rec(category="architecture", effort="unknown", entities=[])
        rec_large = _rec(
            category="architecture",
            effort="unknown",
            entities=["a", "b", "c", "d", "e"],
        )
        estimator.estimate([rec_small])
        estimator.estimate([rec_large])
        small_hours = rec_small.metadata.get("estimated_hours", 0)
        large_hours = rec_large.metadata.get("estimated_hours", 0)
        assert large_hours >= small_hours

    def test_critical_priority_increases_effort_vs_low(self):
        estimator = EffortEstimator()
        rec_crit = _rec(category="security", priority="critical", effort="unknown")
        rec_low = _rec(category="security", priority="low", effort="unknown")
        estimator.estimate([rec_crit])
        estimator.estimate([rec_low])
        assert (
            rec_crit.metadata["estimated_hours"] > rec_low.metadata["estimated_hours"]
        )


# ---------------------------------------------------------------------------
# 5. Roadmap Planner
# ---------------------------------------------------------------------------


class TestRoadmapPlanner:
    def test_critical_items_go_to_phase_1(self):
        planner = RoadmapPlanner()
        rec = _rec(category="documentation", priority="critical")
        phases = planner.plan([rec])
        phase_1 = next((p for p in phases if p.phase == 1), None)
        assert phase_1 is not None
        assert any(r.title == rec.title for r in phase_1.recommendations)

    def test_security_goes_to_phase_1(self):
        planner = RoadmapPlanner()
        rec = _rec(category="security", priority="high")
        phases = planner.plan([rec])
        assert phases[0].phase == 1

    def test_documentation_goes_to_phase_4(self):
        planner = RoadmapPlanner()
        rec = _rec(category="documentation", priority="low")
        phases = planner.plan([rec])
        phase_4 = next((p for p in phases if p.phase == 4), None)
        assert phase_4 is not None

    def test_phases_are_sorted_ascending(self):
        planner = RoadmapPlanner()
        recs = [
            _rec(category="security", priority="high"),
            _rec(category="architecture", priority="medium"),
            _rec(category="documentation", priority="low"),
        ]
        phases = planner.plan(recs)
        phase_nums = [p.phase for p in phases]
        assert phase_nums == sorted(phase_nums)

    def test_empty_phases_are_omitted(self):
        planner = RoadmapPlanner()
        rec = _rec(category="security", priority="high")
        phases = planner.plan([rec])
        assert all(len(p.recommendations) > 0 for p in phases)

    def test_estimated_effort_aggregated_per_phase(self):
        planner = RoadmapPlanner()
        recs = [
            _rec(category="security", priority="high", effort="< 2 hours"),
            _rec(category="dependency", priority="high", effort="Half day"),
        ]
        phases = planner.plan(recs)
        assert phases[0].estimated_total_effort != ""


# ---------------------------------------------------------------------------
# 6. AdvisorService — Full Pipeline
# ---------------------------------------------------------------------------


class TestAdvisorService:
    def test_full_pipeline_produces_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = AdvisorService(base_dir=tmpdir)
            report = svc.advise(
                repo_name="owner/repo",
                inspection_report=_inspection_report(),
                reasoning_result=_reasoning_result(),
                memory_context=_memory_context_degrading(),
                monitoring_run=_monitoring_run_critical(),
            )
            assert isinstance(report, AdvisorReport)
            assert report.repository == "owner/repo"
            assert len(report.recommendations) > 0
            assert len(report.roadmap) > 0
            assert report.overall_priority in ("critical", "high", "medium", "low")

    def test_report_is_persisted_and_loadable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = AdvisorService(base_dir=tmpdir)
            report = svc.advise(
                repo_name="owner/repo",
                inspection_report=_inspection_report(),
            )
            loaded = svc.load_latest("owner/repo")
            assert loaded is not None
            assert loaded.repository == report.repository
            assert loaded.generated_at == report.generated_at

    def test_report_schema_is_complete(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = AdvisorService(base_dir=tmpdir)
            report = svc.advise(
                repo_name="owner/repo",
                inspection_report=_inspection_report(),
            )
            assert "total_recommendations" in report.statistics
            assert "by_priority" in report.statistics
            assert "by_category" in report.statistics
            assert "phases" in report.statistics
            assert "pipeline_stages" in report.metadata

    def test_no_sources_produces_empty_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = AdvisorService(base_dir=tmpdir)
            report = svc.advise(repo_name="owner/empty")
            assert len(report.recommendations) == 0
            assert report.overall_priority == "low"

    def test_duplicates_are_resolved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = AdvisorService(base_dir=tmpdir)
            # Two findings with near-identical titles should be merged
            findings = [
                {
                    "id": "f1",
                    "title": "High coupling between modules",
                    "description": "desc",
                    "category": "architecture",
                    "severity": "high",
                    "confidence": 0.8,
                    "recommendations": ["Apply SOLID principles."],
                    "affected_entities": ["a.py"],
                    "evidence": [],
                    "estimated_effort": "1 day",
                },
                {
                    "id": "f2",
                    "title": "High coupling between modules",
                    "description": "desc",
                    "category": "architecture",
                    "severity": "medium",
                    "confidence": 0.7,
                    "recommendations": [],
                    "affected_entities": ["a.py"],
                    "evidence": [],
                    "estimated_effort": "unknown",
                },
            ]
            report = svc.advise(
                repo_name="owner/repo",
                inspection_report={"findings": findings},
            )
            arch_recs = [
                r for r in report.recommendations if r.category == "architecture"
            ]
            assert len(arch_recs) <= len(findings)

    def test_recommendations_sorted_by_priority(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = AdvisorService(base_dir=tmpdir)
            report = svc.advise(
                repo_name="owner/repo",
                inspection_report=_inspection_report(),
                monitoring_run=_monitoring_run_critical(),
            )
            # First recommendation should be the highest-priority
            scores = [
                r.metadata.get("priority_score", 0) for r in report.recommendations
            ]
            assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# 7. REST Endpoints
# ---------------------------------------------------------------------------


class TestAdvisorRouter:
    def test_post_advisor_returns_404_for_unindexed_repo(self):
        response = client.post("/api/repositories/ghost/nonexistent/advisor")
        assert response.status_code == 404

    def test_get_latest_returns_404_when_no_report(self):
        response = client.get("/api/repositories/ghost/nonexistent/advisor/latest")
        assert response.status_code == 404

    def test_get_recommendations_returns_404_when_no_report(self):
        response = client.get(
            "/api/repositories/ghost/nonexistent/advisor/recommendations"
        )
        assert response.status_code == 404

    def test_get_roadmap_returns_404_when_no_report(self):
        response = client.get("/api/repositories/ghost/nonexistent/advisor/roadmap")
        assert response.status_code == 404

    def test_get_latest_returns_report_when_mocked(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = AdvisorService(base_dir=tmpdir)
            report = svc.advise(
                repo_name="owner/repo",
                inspection_report=_inspection_report(),
                monitoring_run=_monitoring_run_critical(),
            )
            with patch("backend.routers.advisor.advisor_service") as mock_svc:
                mock_svc.load_latest.return_value = report
                response = client.get("/api/repositories/owner/repo/advisor/latest")
                assert response.status_code == 200
                data = response.json()
                assert data["repository"] == "owner/repo"
                assert "recommendations" in data
                assert "roadmap" in data

    def test_get_recommendations_with_priority_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = AdvisorService(base_dir=tmpdir)
            report = svc.advise(
                repo_name="owner/repo",
                inspection_report=_inspection_report(),
                monitoring_run=_monitoring_run_critical(),
            )
            with patch("backend.routers.advisor.advisor_service") as mock_svc:
                mock_svc.load_latest.return_value = report
                response = client.get(
                    "/api/repositories/owner/repo/advisor/recommendations?priority=critical"
                )
                assert response.status_code == 200
                data = response.json()
                assert all(r["priority"] == "critical" for r in data)

    def test_get_roadmap_returns_ordered_phases(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = AdvisorService(base_dir=tmpdir)
            report = svc.advise(
                repo_name="owner/repo",
                inspection_report=_inspection_report(),
                monitoring_run=_monitoring_run_critical(),
            )
            with patch("backend.routers.advisor.advisor_service") as mock_svc:
                mock_svc.load_latest.return_value = report
                response = client.get("/api/repositories/owner/repo/advisor/roadmap")
                assert response.status_code == 200
                phases = response.json()
                phase_nums = [p["phase"] for p in phases]
                assert phase_nums == sorted(phase_nums)
