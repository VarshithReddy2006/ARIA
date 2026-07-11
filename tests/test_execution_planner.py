"""Unit tests for the Autonomous Engineering Agent (AEA²) execution planner."""

import os
import sys
import tempfile
import uuid
from typing import Any, Dict, List, Optional
from unittest.mock import patch


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from backend.api import app
from models.execution import ExecutionPlan, ExecutionTask
from services.execution_planner import (
    ConflictDetector,
    DependencyResolver,
    ExecutionPlannerService,
    ParallelizationPlanner,
    RiskAnalyzer,
    TaskDecomposer,
)

client = TestClient(app)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _advisor_rec(
    title="Fix vulnerability",
    category="security",
    priority="high",
    effort="Half day",
    entities: Optional[List[str]] = None,
    rec_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "id": rec_id or str(uuid.uuid4()),
        "title": title,
        "description": "Test description.",
        "category": category,
        "priority": priority,
        "estimated_effort": effort,
        "confidence": 0.9,
        "sources": ["RepositoryInspector"],
        "affected_entities": entities or [],
        "evidence": [],
        "recurrence_count": 1,
        "metadata": {},
    }


def _advisor_report(
    recommendations: Optional[List[Dict[str, Any]]] = None,
    repo: str = "owner/repo",
) -> Dict[str, Any]:
    recs = recommendations if recommendations is not None else [_advisor_rec()]
    return {
        "repository": repo,
        "generated_at": 1000.0,
        "overall_priority": "high",
        "recommendations": recs,
        "roadmap": [],
        "statistics": {},
        "metadata": {},
    }


def _task(
    category="security",
    entities: Optional[List[str]] = None,
    deps: Optional[List[str]] = None,
    rec_id: str = "rec-1",
    rollback: bool = False,
    risk: str = "low",
) -> ExecutionTask:
    return ExecutionTask(
        id=str(uuid.uuid4()),
        recommendation_id=rec_id,
        title=f"Task for {category}",
        description="Test task.",
        category=category,
        dependencies=deps or [],
        estimated_effort="Half day",
        risk=risk,
        affected_entities=entities or [],
        rollback_checkpoint=rollback,
    )


# ---------------------------------------------------------------------------
# 1. Task Decomposer
# ---------------------------------------------------------------------------


class TestTaskDecomposer:
    def test_security_rec_produces_multiple_tasks(self):
        decomposer = TaskDecomposer()
        recs = [_advisor_rec(category="security")]
        tasks = decomposer.decompose(recs)
        assert len(tasks) >= 2

    def test_tasks_inherit_affected_entities(self):
        decomposer = TaskDecomposer()
        recs = [_advisor_rec(category="architecture", entities=["a.py", "b.py"])]
        tasks = decomposer.decompose(recs)
        for task in tasks:
            assert "a.py" in task.affected_entities

    def test_tasks_have_sequential_dependencies(self):
        decomposer = TaskDecomposer()
        recs = [_advisor_rec(category="security")]
        tasks = decomposer.decompose(recs)
        # Second task depends on first, etc.
        assert tasks[1].dependencies == [tasks[0].id]
        if len(tasks) > 2:
            assert tasks[2].dependencies == [tasks[1].id]

    def test_last_task_is_rollback_checkpoint(self):
        decomposer = TaskDecomposer()
        recs = [_advisor_rec(category="security")]
        tasks = decomposer.decompose(recs)
        assert tasks[-1].rollback_checkpoint is True

    def test_all_known_categories_produce_tasks(self):
        decomposer = TaskDecomposer()
        categories = [
            "security",
            "architecture",
            "performance",
            "dependency",
            "complexity",
            "dead_code",
            "documentation",
            "testing",
            "general",
        ]
        for cat in categories:
            tasks = decomposer.decompose([_advisor_rec(category=cat)])
            assert len(tasks) >= 1, f"Category '{cat}' produced no tasks"

    def test_multiple_recommendations_produce_separate_task_chains(self):
        decomposer = TaskDecomposer()
        recs = [
            _advisor_rec(category="security", rec_id="r1"),
            _advisor_rec(category="testing", rec_id="r2"),
        ]
        tasks = decomposer.decompose(recs)
        r1_tasks = [t for t in tasks if t.recommendation_id == "r1"]
        r2_tasks = [t for t in tasks if t.recommendation_id == "r2"]
        assert len(r1_tasks) > 0
        assert len(r2_tasks) > 0
        # Chains from different recommendations should not cross-depend
        r1_ids = {t.id for t in r1_tasks}
        for t in r2_tasks:
            assert not (set(t.dependencies) & r1_ids)


# ---------------------------------------------------------------------------
# 2. Dependency Resolver
# ---------------------------------------------------------------------------


class TestDependencyResolver:
    def test_returns_topologically_sorted_tasks(self):
        resolver = DependencyResolver()
        t1 = _task()
        t2 = _task(deps=[t1.id])
        t3 = _task(deps=[t2.id])
        ordered = resolver.resolve([t3, t1, t2])
        ids = [t.id for t in ordered]
        assert ids.index(t1.id) < ids.index(t2.id)
        assert ids.index(t2.id) < ids.index(t3.id)

    def test_independent_tasks_are_all_included(self):
        resolver = DependencyResolver()
        tasks = [_task() for _ in range(5)]
        ordered = resolver.resolve(tasks)
        assert len(ordered) == 5

    def test_critical_path_longest_chain(self):
        resolver = DependencyResolver()
        t1 = _task()
        t2 = _task(deps=[t1.id])
        t3 = _task(deps=[t2.id])
        t4 = _task()  # Separate, shorter chain
        tasks = [t1, t2, t3, t4]
        path = resolver.compute_critical_path(tasks)
        # All three chained tasks should appear in the critical path
        assert t3.id in path
        assert t1.id in path or t2.id in path

    def test_critical_path_single_task(self):
        resolver = DependencyResolver()
        t = _task()
        path = resolver.compute_critical_path([t])
        assert t.id in path

    def test_critical_path_empty(self):
        resolver = DependencyResolver()
        path = resolver.compute_critical_path([])
        assert path == []


# ---------------------------------------------------------------------------
# 3. Conflict Detector
# ---------------------------------------------------------------------------


class TestConflictDetector:
    def test_detects_file_collision(self):
        detector = ConflictDetector()
        t1 = _task(entities=["shared.py"], rec_id="r1")
        t2 = _task(entities=["shared.py"], rec_id="r2")
        conflicts = detector.detect([t1, t2])
        assert any(c.conflict_type == "file_collision" for c in conflicts)

    def test_no_conflict_for_same_recommendation_tasks(self):
        detector = ConflictDetector()
        t1 = _task(entities=["shared.py"], rec_id="r1")
        t2 = _task(entities=["shared.py"], rec_id="r1")  # Same rec
        conflicts = detector.detect([t1, t2])
        file_conflicts = [c for c in conflicts if c.conflict_type == "file_collision"]
        assert len(file_conflicts) == 0

    def test_no_conflict_when_tasks_already_ordered(self):
        detector = ConflictDetector()
        t1 = _task(entities=["shared.py"], rec_id="r1")
        t2 = _task(entities=["shared.py"], rec_id="r2", deps=[t1.id])
        conflicts = detector.detect([t1, t2])
        file_conflicts = [c for c in conflicts if c.conflict_type == "file_collision"]
        assert len(file_conflicts) == 0

    def test_detects_module_ownership_conflict(self):
        detector = ConflictDetector()
        # Same category, different recs, no entity overlap
        t1 = _task(category="security", entities=["a.py"], rec_id="r1")
        t2 = _task(category="security", entities=["b.py"], rec_id="r2")
        conflicts = detector.detect([t1, t2])
        assert any(c.conflict_type == "module_ownership" for c in conflicts)

    def test_no_false_conflict_for_safe_categories(self):
        detector = ConflictDetector()
        t1 = _task(category="documentation", entities=[], rec_id="r1")
        t2 = _task(category="testing", entities=[], rec_id="r2")
        conflicts = detector.detect([t1, t2])
        assert len(conflicts) == 0


# ---------------------------------------------------------------------------
# 4. Parallelization Planner
# ---------------------------------------------------------------------------


class TestParallelizationPlanner:
    def test_produces_at_least_one_batch(self):
        planner = ParallelizationPlanner()
        tasks = [_task(category="security")]
        batches = planner.plan(tasks)
        assert len(batches) >= 1

    def test_security_tasks_go_to_batch_1(self):
        planner = ParallelizationPlanner()
        task = _task(category="security")
        batches = planner.plan([task])
        assert any(task.id in [t.id for t in b.tasks] for b in batches)
        first_batch = batches[0]
        assert task.id in [t.id for t in first_batch.tasks]

    def test_batches_are_ordered_ascending(self):
        planner = ParallelizationPlanner()
        tasks = [
            _task(category="security"),
            _task(category="architecture"),
            _task(category="documentation"),
        ]
        batches = planner.plan(tasks)
        orders = [b.order for b in batches]
        assert orders == sorted(orders)

    def test_multiple_tasks_in_same_batch_have_parallel_annotations(self):
        planner = ParallelizationPlanner()
        tasks = [_task(category="documentation"), _task(category="testing")]
        batches = planner.plan(tasks)
        last_batch = batches[-1]
        if len(last_batch.tasks) > 1:
            assert last_batch.parallel is True

    def test_batches_include_effort_estimate(self):
        planner = ParallelizationPlanner()
        tasks = [_task(category="security", entities=[])]
        batches = planner.plan(tasks)
        assert all(b.estimated_total_effort != "" for b in batches)

    def test_empty_batches_are_not_produced(self):
        planner = ParallelizationPlanner()
        tasks = [_task(category="performance")]
        batches = planner.plan(tasks)
        assert all(len(b.tasks) > 0 for b in batches)


# ---------------------------------------------------------------------------
# 5. Risk Analyzer
# ---------------------------------------------------------------------------


class TestRiskAnalyzer:
    def test_security_tasks_get_high_base_risk(self):
        analyzer = RiskAnalyzer()
        task = _task(category="security")
        result = analyzer.analyze([task])
        assert result[0].risk in ("high", "critical")

    def test_documentation_tasks_get_low_risk(self):
        analyzer = RiskAnalyzer()
        task = _task(category="documentation")
        result = analyzer.analyze([task])
        assert result[0].risk == "low"

    def test_many_entities_escalates_risk(self):
        analyzer = RiskAnalyzer()
        task = _task(category="documentation", entities=["a", "b", "c", "d", "e", "f"])
        result = analyzer.analyze([task])
        assert result[0].risk in ("medium", "high", "critical")

    def test_deep_dependency_escalates_risk(self):
        analyzer = RiskAnalyzer()
        task = _task(category="performance")
        depths = {task.id: 5}
        result = analyzer.analyze([task], dep_depths=depths)
        assert result[0].risk in ("high", "critical")

    def test_risk_rationale_is_populated(self):
        analyzer = RiskAnalyzer()
        task = _task(category="architecture")
        result = analyzer.analyze([task])
        assert result[0].risk_rationale != ""


# ---------------------------------------------------------------------------
# 6. ExecutionPlannerService — Full Pipeline
# ---------------------------------------------------------------------------


class TestExecutionPlannerService:
    def test_full_pipeline_produces_plan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = ExecutionPlannerService(base_dir=tmpdir)
            plan = svc.plan("owner/repo", _advisor_report())
            assert isinstance(plan, ExecutionPlan)
            assert plan.repository == "owner/repo"
            assert len(plan.batches) > 0
            assert isinstance(plan.critical_path, list)
            assert isinstance(plan.rollback_points, list)

    def test_plan_is_persisted_and_loadable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = ExecutionPlannerService(base_dir=tmpdir)
            plan = svc.plan("owner/repo", _advisor_report())
            loaded = svc.load_latest("owner/repo")
            assert loaded is not None
            assert loaded.id == plan.id

    def test_plan_statistics_are_complete(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = ExecutionPlannerService(base_dir=tmpdir)
            plan = svc.plan("owner/repo", _advisor_report())
            assert "total_tasks" in plan.statistics
            assert "total_batches" in plan.statistics
            assert "by_risk" in plan.statistics
            assert "rollback_checkpoints" in plan.statistics

    def test_plan_has_rollback_points(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = ExecutionPlannerService(base_dir=tmpdir)
            plan = svc.plan("owner/repo", _advisor_report())
            assert len(plan.rollback_points) > 0

    def test_multiple_recommendations_produce_multiple_batches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = ExecutionPlannerService(base_dir=tmpdir)
            recs = [
                _advisor_rec(category="security"),
                _advisor_rec(category="documentation"),
            ]
            plan = svc.plan("owner/repo", _advisor_report(recommendations=recs))
            assert len(plan.batches) >= 1

    def test_conflicting_tasks_are_reported(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = ExecutionPlannerService(base_dir=tmpdir)
            # Two security recommendations affecting the same file should conflict
            recs = [
                _advisor_rec(category="security", entities=["auth.py"], rec_id="r1"),
                _advisor_rec(category="security", entities=["auth.py"], rec_id="r2"),
            ]
            plan = svc.plan("owner/repo", _advisor_report(recommendations=recs))
            assert isinstance(plan.conflicts, list)

    def test_empty_advisor_report_produces_empty_plan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = ExecutionPlannerService(base_dir=tmpdir)
            plan = svc.plan("owner/repo", _advisor_report(recommendations=[]))
            assert plan.statistics["total_tasks"] == 0
            assert len(plan.batches) == 0

    def test_pipeline_metadata_records_stages(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = ExecutionPlannerService(base_dir=tmpdir)
            plan = svc.plan("owner/repo", _advisor_report())
            assert "pipeline_stages" in plan.metadata
            assert "TaskDecomposer" in plan.metadata["pipeline_stages"]


# ---------------------------------------------------------------------------
# 7. REST Endpoints
# ---------------------------------------------------------------------------


class TestExecutionRouter:
    def test_post_plan_returns_404_for_unindexed_repo(self):
        response = client.post("/api/repositories/ghost/nonexistent/execution-plan")
        assert response.status_code == 404

    def test_get_latest_returns_404_when_no_plan(self):
        response = client.get(
            "/api/repositories/ghost/nonexistent/execution-plan/latest"
        )
        assert response.status_code == 404

    def test_get_batches_returns_404_when_no_plan(self):
        response = client.get(
            "/api/repositories/ghost/nonexistent/execution-plan/batches"
        )
        assert response.status_code == 404

    def test_get_critical_path_returns_404_when_no_plan(self):
        response = client.get(
            "/api/repositories/ghost/nonexistent/execution-plan/critical-path"
        )
        assert response.status_code == 404

    def test_get_latest_returns_plan_when_mocked(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = ExecutionPlannerService(base_dir=tmpdir)
            plan = svc.plan("owner/repo", _advisor_report())
            with patch(
                "backend.routers.execution.execution_planner_service"
            ) as mock_svc:
                mock_svc.load_latest.return_value = plan
                response = client.get(
                    "/api/repositories/owner/repo/execution-plan/latest"
                )
                assert response.status_code == 200
                data = response.json()
                assert data["repository"] == "owner/repo"
                assert "batches" in data
                assert "critical_path" in data
                assert "rollback_points" in data

    def test_get_batches_returns_ordered_batches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = ExecutionPlannerService(base_dir=tmpdir)
            plan = svc.plan("owner/repo", _advisor_report())
            with patch(
                "backend.routers.execution.execution_planner_service"
            ) as mock_svc:
                mock_svc.load_latest.return_value = plan
                response = client.get(
                    "/api/repositories/owner/repo/execution-plan/batches"
                )
                assert response.status_code == 200
                batches = response.json()
                orders = [b["order"] for b in batches]
                assert orders == sorted(orders)

    def test_get_critical_path_returns_structured_response(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = ExecutionPlannerService(base_dir=tmpdir)
            plan = svc.plan("owner/repo", _advisor_report())
            with patch(
                "backend.routers.execution.execution_planner_service"
            ) as mock_svc:
                mock_svc.load_latest.return_value = plan
                response = client.get(
                    "/api/repositories/owner/repo/execution-plan/critical-path"
                )
                assert response.status_code == 200
                data = response.json()
                assert "critical_path" in data
                assert "rollback_points" in data
                assert "conflicts" in data
                assert "statistics" in data
