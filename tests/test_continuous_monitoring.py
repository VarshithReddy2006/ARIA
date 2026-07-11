"""Unit tests for the Continuous Repository Monitoring (CRM) subsystem."""

import sys
import os
import tempfile
from unittest.mock import MagicMock, patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from backend.api import app

from models.inspection import InspectionReport
from models.monitoring import MonitoringRun, MonitoringStatus, RepositoryHealthTrend
from services.continuous_monitoring import (
    ChangeDetector,
    CommitThresholdPolicy,
    ContinuousMonitoringService,
    HealthTrendEngine,
    ImmediatePolicy,
    ManualPolicy,
    MonitoringScheduler,
    TimeBasedPolicy,
)

client = TestClient(app)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run(
    repo="owner/repo",
    trigger="indexing",
    policy="immediate",
    status="completed",
    overall_score=85.0,
    timestamp=1000.0,
) -> MonitoringRun:
    return MonitoringRun(
        id="test-run-id",
        repository=repo,
        timestamp=timestamp,
        trigger=trigger,
        policy=policy,
        inspection_report_path="",
        status=status,
        duration_ms=120.0,
        overall_score=overall_score,
        finding_counts={"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 0},
    )


def _make_report(timestamp=1000.0, findings=None) -> dict:
    findings = findings or [
        {"category": "architecture", "severity": "high", "confidence": 0.9},
        {"category": "security", "severity": "medium", "confidence": 0.8},
    ]
    return {"timestamp": timestamp, "findings": findings, "overall_score": 85.0}


def _mock_inspector(overall_score=88.0, base_dir=None) -> MagicMock:
    """Returns a mock RepositoryInspector that returns a fixed InspectionReport."""
    inspector = MagicMock()
    inspector._get_repo_dir.return_value = base_dir or tempfile.mkdtemp()
    report = MagicMock(spec=InspectionReport)
    report.overall_score = overall_score
    report.statistics = {"by_severity": {"critical": 0, "high": 1}}
    inspector.inspect.return_value = report
    return inspector


# ---------------------------------------------------------------------------
# 1. Monitoring Policies
# ---------------------------------------------------------------------------


class TestMonitoringPolicies:
    def test_immediate_triggers_on_indexing(self):
        assert ImmediatePolicy().should_run({"trigger": "indexing"})

    def test_immediate_triggers_on_push(self):
        assert ImmediatePolicy().should_run({"trigger": "push"})

    def test_immediate_does_not_trigger_on_manual(self):
        assert not ImmediatePolicy().should_run({"trigger": "manual"})

    def test_commit_threshold_triggers_at_threshold(self):
        assert CommitThresholdPolicy(threshold=5).should_run({"commit_count": 5})

    def test_commit_threshold_triggers_above_threshold(self):
        assert CommitThresholdPolicy(threshold=5).should_run({"commit_count": 10})

    def test_commit_threshold_does_not_trigger_below(self):
        assert not CommitThresholdPolicy(threshold=5).should_run({"commit_count": 3})

    def test_time_based_triggers_after_interval(self):
        import time

        policy = TimeBasedPolicy(interval_seconds=60)
        old_ts = time.time() - 120
        assert policy.should_run({"last_run_timestamp": old_ts})

    def test_time_based_does_not_trigger_too_soon(self):
        import time

        policy = TimeBasedPolicy(interval_seconds=3600)
        recent_ts = time.time() - 30
        assert not policy.should_run({"last_run_timestamp": recent_ts})

    def test_manual_triggers_on_manual(self):
        assert ManualPolicy().should_run({"trigger": "manual"})

    def test_manual_does_not_trigger_on_indexing(self):
        assert not ManualPolicy().should_run({"trigger": "indexing"})


# ---------------------------------------------------------------------------
# 2. Monitoring Scheduler
# ---------------------------------------------------------------------------


class TestMonitoringScheduler:
    def test_authorized_when_policy_allows(self):
        scheduler = MonitoringScheduler(ImmediatePolicy())
        assert scheduler.is_authorized({"trigger": "indexing"})

    def test_not_authorized_when_policy_denies(self):
        scheduler = MonitoringScheduler(ManualPolicy())
        assert not scheduler.is_authorized({"trigger": "indexing"})


# ---------------------------------------------------------------------------
# 3. Change Detector
# ---------------------------------------------------------------------------


class TestChangeDetector:
    def test_detects_reindex(self):
        detector = ChangeDetector()
        changes = detector.detect({"trigger": "indexing"})
        assert changes["has_reindex"] is True
        assert changes["is_significant"] is True

    def test_detects_new_commits(self):
        detector = ChangeDetector()
        changes = detector.detect({"trigger": "push", "commit_count": 3})
        assert changes["has_new_commits"] is True

    def test_detects_health_degradation(self):
        detector = ChangeDetector()
        last_run = _make_run(overall_score=90.0)
        changes = detector.detect(
            {"trigger": "push", "current_health_score": 80.0}, last_run
        )
        assert changes["has_health_degradation"] is True

    def test_no_health_degradation_when_stable(self):
        detector = ChangeDetector()
        last_run = _make_run(overall_score=85.0)
        changes = detector.detect(
            {"trigger": "push", "current_health_score": 83.0}, last_run
        )
        assert changes["has_health_degradation"] is False

    def test_not_significant_when_no_changes(self):
        detector = ChangeDetector()
        # A manual event with no structural signals
        changes = detector.detect({"trigger": "manual"})
        # trigger=manual → has_reindex=False, has_new_commits=False, etc.
        assert changes["is_significant"] is False


# ---------------------------------------------------------------------------
# 4. Health Trend Engine
# ---------------------------------------------------------------------------


class TestHealthTrendEngine:
    def test_builds_trend_from_runs(self):
        engine = HealthTrendEngine()
        runs = [
            _make_run(overall_score=80.0, timestamp=1000.0),
            _make_run(overall_score=85.0, timestamp=2000.0),
            _make_run(overall_score=90.0, timestamp=3000.0),
        ]
        reports = [_make_report(ts, []) for ts in [1000.0, 2000.0, 3000.0]]
        trend = engine.build_trend(runs, reports)
        assert trend.repository == "owner/repo"
        assert len(trend.overall_scores) == 3
        assert trend.trend == "Improving"

    def test_detects_degrading_trend(self):
        engine = HealthTrendEngine()
        runs = [
            _make_run(overall_score=95.0, timestamp=1000.0),
            _make_run(overall_score=85.0, timestamp=2000.0),
            _make_run(overall_score=75.0, timestamp=3000.0),
        ]
        trend = engine.build_trend(runs, [])
        assert trend.trend == "Degrading"

    def test_detects_stable_trend(self):
        engine = HealthTrendEngine()
        runs = [
            _make_run(overall_score=80.0, timestamp=1000.0),
            _make_run(overall_score=81.0, timestamp=2000.0),
        ]
        trend = engine.build_trend(runs, [])
        assert trend.trend == "Stable"

    def test_empty_runs_returns_default(self):
        engine = HealthTrendEngine()
        trend = engine.build_trend([], [])
        assert trend.repository == ""

    def test_computes_category_scores(self):
        engine = HealthTrendEngine()
        findings = [
            {"category": "architecture", "severity": "high", "confidence": 1.0},
            {"category": "security", "severity": "critical", "confidence": 1.0},
        ]
        runs = [_make_run(overall_score=60.0, timestamp=1000.0)]
        reports = [_make_report(1000.0, findings)]
        trend = engine.build_trend(runs, reports)
        assert trend.architecture_scores[0] < 100.0
        assert trend.security_scores[0] < 100.0


# ---------------------------------------------------------------------------
# 5. ContinuousMonitoringService — Pipeline Orchestration
# ---------------------------------------------------------------------------


class TestContinuousMonitoringService:
    def test_trigger_completed_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            inspector = _mock_inspector(base_dir=tmpdir)
            svc = ContinuousMonitoringService(
                repository_inspector=inspector,
                base_dir=tmpdir,
                default_policy=ImmediatePolicy(),
            )
            run = svc.trigger(
                repo_name="owner/repo",
                twin_data={},
                knowledge_graph_data={},
                repository_event={"trigger": "indexing"},
            )
            assert run.status == "completed"
            assert run.overall_score == 88.0
            assert run.trigger == "indexing"

    def test_trigger_skipped_when_policy_denies(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            inspector = _mock_inspector(base_dir=tmpdir)
            svc = ContinuousMonitoringService(
                repository_inspector=inspector,
                base_dir=tmpdir,
                default_policy=ManualPolicy(),
            )
            run = svc.trigger(
                repo_name="owner/repo",
                twin_data={},
                knowledge_graph_data={},
                repository_event={"trigger": "indexing"},
                policy=ManualPolicy(),
            )
            assert run.status == "skipped"
            inspector.inspect.assert_not_called()

    def test_run_is_persisted_and_loadable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            inspector = _mock_inspector(base_dir=tmpdir)
            svc = ContinuousMonitoringService(
                repository_inspector=inspector,
                base_dir=tmpdir,
                default_policy=ImmediatePolicy(),
            )
            svc.trigger(
                repo_name="owner/repo",
                twin_data={},
                knowledge_graph_data={},
                repository_event={"trigger": "indexing"},
            )
            loaded = svc.load_latest_run("owner/repo")
            assert loaded is not None
            assert loaded.repository == "owner/repo"
            assert loaded.status == "completed"

    def test_history_returns_multiple_runs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            inspector = _mock_inspector(base_dir=tmpdir)
            svc = ContinuousMonitoringService(
                repository_inspector=inspector,
                base_dir=tmpdir,
                default_policy=ImmediatePolicy(),
            )
            for _ in range(3):
                svc.trigger(
                    repo_name="owner/repo",
                    twin_data={},
                    knowledge_graph_data={},
                    repository_event={"trigger": "indexing"},
                )
            history = svc.load_history("owner/repo")
            assert len(history) == 3

    def test_trend_is_generated_after_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            inspector = _mock_inspector(base_dir=tmpdir)
            svc = ContinuousMonitoringService(
                repository_inspector=inspector,
                base_dir=tmpdir,
                default_policy=ImmediatePolicy(),
            )
            svc.trigger(
                repo_name="owner/repo",
                twin_data={},
                knowledge_graph_data={},
                repository_event={"trigger": "indexing"},
            )
            trend = svc.load_trend("owner/repo")
            assert trend is not None
            assert len(trend.overall_scores) == 1

    def test_status_reflects_latest_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            inspector = _mock_inspector(base_dir=tmpdir)
            svc = ContinuousMonitoringService(
                repository_inspector=inspector,
                base_dir=tmpdir,
                default_policy=ImmediatePolicy(),
            )
            svc.trigger(
                repo_name="owner/repo",
                twin_data={},
                knowledge_graph_data={},
                repository_event={"trigger": "indexing"},
            )
            status = svc.get_status("owner/repo")
            assert status.total_runs == 1
            assert status.last_run_status == "completed"
            assert status.last_overall_score == 88.0

    def test_status_when_no_runs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = ContinuousMonitoringService(base_dir=tmpdir)
            status = svc.get_status("owner/empty")
            assert status.total_runs == 0
            assert status.last_run_timestamp is None

    def test_inspector_integration_not_called_without_attachment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = ContinuousMonitoringService(
                repository_inspector=None,
                base_dir=tmpdir,
                default_policy=ImmediatePolicy(),
            )
            run = svc.trigger(
                repo_name="owner/repo",
                twin_data={},
                knowledge_graph_data={},
                repository_event={"trigger": "indexing"},
            )
            assert run.status == "completed"
            assert run.overall_score == 100.0


# ---------------------------------------------------------------------------
# 6. REST Endpoints
# ---------------------------------------------------------------------------


class TestMonitoringRouter:
    def test_post_monitor_returns_404_for_unindexed_repo(self):
        response = client.post("/api/repositories/ghost/nonexistent/monitor")
        assert response.status_code == 404

    def test_get_latest_returns_404_when_no_runs(self):
        response = client.get("/api/repositories/ghost/nonexistent/monitor/latest")
        assert response.status_code == 404

    def test_get_history_returns_empty_list_when_no_runs(self):
        # History endpoint returns an empty list (not a 404) when no runs exist
        response = client.get("/api/repositories/ghost/nonexistent/monitor/history")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_trends_returns_404_when_no_data(self):
        response = client.get("/api/repositories/ghost/nonexistent/monitor/trends")
        assert response.status_code == 404

    def test_get_status_returns_empty_status(self):
        response = client.get("/api/repositories/ghost/nonexistent/monitor/status")
        assert response.status_code == 200
        data = response.json()
        assert data["total_runs"] == 0
        assert data["last_run_timestamp"] is None

    def test_get_latest_returns_run_when_mocked(self):
        with patch(
            "backend.routers.monitoring.continuous_monitoring_service"
        ) as mock_svc:
            mock_svc.load_latest_run.return_value = _make_run()
            response = client.get("/api/repositories/owner/repo/monitor/latest")
            assert response.status_code == 200
            data = response.json()
            assert data["overall_score"] == 85.0
            assert data["status"] == "completed"

    def test_get_trends_returns_trend_when_mocked(self):
        with patch(
            "backend.routers.monitoring.continuous_monitoring_service"
        ) as mock_svc:
            mock_trend = RepositoryHealthTrend(
                repository="owner/repo",
                timestamps=[1000.0, 2000.0],
                overall_scores=[80.0, 85.0],
                architecture_scores=[75.0, 82.0],
                security_scores=[90.0, 88.0],
                maintainability_scores=[85.0, 87.0],
                trend="Improving",
                confidence=0.8,
            )
            mock_svc.load_trend.return_value = mock_trend
            response = client.get("/api/repositories/owner/repo/monitor/trends")
            assert response.status_code == 200
            data = response.json()
            assert data["trend"] == "Improving"
            assert data["confidence"] == 0.8

    def test_get_status_returns_mocked_status(self):
        with patch(
            "backend.routers.monitoring.continuous_monitoring_service"
        ) as mock_svc:
            mock_svc.get_status.return_value = MonitoringStatus(
                repository="owner/repo",
                total_runs=5,
                last_run_timestamp=1000.0,
                last_run_status="completed",
                last_overall_score=88.0,
                current_trend="Improving",
                active_policy="immediate",
            )
            response = client.get("/api/repositories/owner/repo/monitor/status")
            assert response.status_code == 200
            data = response.json()
            assert data["total_runs"] == 5
            assert data["current_trend"] == "Improving"
