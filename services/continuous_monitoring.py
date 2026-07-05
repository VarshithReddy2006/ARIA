"""Continuous Repository Monitoring (CRM) — Service Layer.

Implements:
  MonitoringPolicy (ABC) + built-in strategies
  ChangeDetector
  MonitoringScheduler
  HealthTrendEngine
  ContinuousMonitoringService
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from models.monitoring import MonitoringRun, MonitoringStatus, RepositoryHealthTrend

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Severity order (shared constant)
# ---------------------------------------------------------------------------
_SEVERITY_ORDER = ("critical", "high", "medium", "low", "info")

# ---------------------------------------------------------------------------
# 1. Monitoring Policies
# ---------------------------------------------------------------------------


class MonitoringPolicy(ABC):
    """Abstract base class for all monitoring policies."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def should_run(self, repository_event: Dict[str, Any]) -> bool:
        """Returns True if a monitoring run should execute given the repository event."""
        ...


class ImmediatePolicy(MonitoringPolicy):
    """Triggers after every successful indexing operation."""

    name = "immediate"

    def should_run(self, repository_event: Dict[str, Any]) -> bool:
        return repository_event.get("trigger") in ("indexing", "reindex", "push")


class CommitThresholdPolicy(MonitoringPolicy):
    """Triggers once N or more new commits have been detected."""

    name = "commit_threshold"

    def __init__(self, threshold: int = 5) -> None:
        self.threshold = threshold

    def should_run(self, repository_event: Dict[str, Any]) -> bool:
        commit_count = int(repository_event.get("commit_count", 0))
        return commit_count >= self.threshold


class TimeBasedPolicy(MonitoringPolicy):
    """Triggers when at least `interval_seconds` have elapsed since the last run."""

    name = "time_based"

    def __init__(self, interval_seconds: int = 3600) -> None:
        self.interval_seconds = interval_seconds

    def should_run(self, repository_event: Dict[str, Any]) -> bool:
        last_run_ts = float(repository_event.get("last_run_timestamp", 0.0))
        return (time.time() - last_run_ts) >= self.interval_seconds


class ManualPolicy(MonitoringPolicy):
    """Only executes via explicit REST trigger."""

    name = "manual"

    def should_run(self, repository_event: Dict[str, Any]) -> bool:
        return repository_event.get("trigger") == "manual"


# ---------------------------------------------------------------------------
# 2. Change Detector
# ---------------------------------------------------------------------------


class ChangeDetector:
    """Determines whether a repository has changed in a way that warrants monitoring.

    Never analyzes code. Only inspects event metadata.
    """

    _COMMIT_FIELDS = {"commit_count", "new_commits", "commit_sha"}
    _ARCH_FIELDS = {"architecture_changed", "dependency_changed"}

    def detect(
        self,
        repository_event: Dict[str, Any],
        last_run: Optional[MonitoringRun] = None,
    ) -> Dict[str, Any]:
        """Returns a structured change summary for the monitoring pipeline."""
        trigger = repository_event.get("trigger", "unknown")
        changes: Dict[str, Any] = {
            "trigger": trigger,
            "has_new_commits": any(k in repository_event for k in self._COMMIT_FIELDS),
            "has_reindex": trigger in ("indexing", "reindex"),
            "has_dependency_update": bool(repository_event.get("dependency_changed")),
            "has_architecture_change": bool(repository_event.get("architecture_changed")),
            "has_health_degradation": self._detect_health_degradation(repository_event, last_run),
            "has_memory_event": bool(repository_event.get("memory_event")),
        }
        changes["is_significant"] = any(
            v for k, v in changes.items() if k != "trigger"
        )
        return changes

    def _detect_health_degradation(
        self,
        event: Dict[str, Any],
        last_run: Optional[MonitoringRun],
    ) -> bool:
        """Returns True if the most recent score has dropped significantly."""
        if last_run is None:
            return False
        current_score = float(event.get("current_health_score", 100.0))
        return current_score < (last_run.overall_score - 5.0)


# ---------------------------------------------------------------------------
# 3. Monitoring Scheduler
# ---------------------------------------------------------------------------


class MonitoringScheduler:
    """Evaluates which monitoring policy authorizes execution for the current event."""

    def __init__(self, policy: MonitoringPolicy) -> None:
        self.policy = policy

    def is_authorized(self, repository_event: Dict[str, Any]) -> bool:
        """Returns True when the active policy permits a monitoring run."""
        return self.policy.should_run(repository_event)


# ---------------------------------------------------------------------------
# 4. Health Trend Engine
# ---------------------------------------------------------------------------


class HealthTrendEngine:
    """Generates deterministic repository health trends from monitoring run history."""

    # Severity weights for per-category scoring
    _SEVERITY_WEIGHTS = {"critical": 20.0, "high": 10.0, "medium": 5.0, "low": 2.0, "info": 0.5}
    _ARCH_CATEGORIES = {"architecture", "complexity"}
    _SEC_CATEGORIES = {"security", "dependency"}
    _MAINT_CATEGORIES = {"dead_code", "documentation", "testing"}

    def _category_score(self, findings: List[Dict[str, Any]], target_categories: set) -> float:
        """Computes a 0–100 score for a subset of finding categories."""
        relevant = [f for f in findings if f.get("category") in target_categories]
        deduction = sum(
            self._SEVERITY_WEIGHTS.get(f.get("severity", "info"), 0) * float(f.get("confidence", 0.8))
            for f in relevant
        )
        return round(max(0.0, 100.0 - deduction), 1)

    def _linear_trend(self, scores: List[float]) -> tuple[str, float]:
        """Derives trend direction and confidence from a list of scores."""
        if len(scores) < 2:
            return "stable", 1.0
        delta = scores[-1] - scores[0]
        confidence = min(1.0, len(scores) / 10.0)
        if delta > 5.0:
            return "Improving", round(confidence, 2)
        if delta < -5.0:
            return "Degrading", round(confidence, 2)
        return "Stable", round(confidence, 2)

    def build_trend(
        self,
        runs: List[MonitoringRun],
        inspection_reports: List[Dict[str, Any]],
    ) -> RepositoryHealthTrend:
        """Computes a RepositoryHealthTrend from chronological runs and their reports."""
        if not runs:
            return RepositoryHealthTrend(repository="")

        timestamps, overall, arch, sec, maint = [], [], [], [], []

        for run in sorted(runs, key=lambda r: r.timestamp):
            report = next(
                (rep for rep in inspection_reports if rep.get("timestamp") == run.timestamp),
                None,
            )
            findings = report.get("findings", []) if report else []

            timestamps.append(run.timestamp)
            overall.append(run.overall_score)
            arch.append(self._category_score(findings, self._ARCH_CATEGORIES))
            sec.append(self._category_score(findings, self._SEC_CATEGORIES))
            maint.append(self._category_score(findings, self._MAINT_CATEGORIES))

        trend_label, confidence = self._linear_trend(overall)

        return RepositoryHealthTrend(
            repository=runs[0].repository,
            timestamps=timestamps,
            overall_scores=overall,
            architecture_scores=arch,
            security_scores=sec,
            maintainability_scores=maint,
            trend=trend_label,
            confidence=confidence,
        )


# ---------------------------------------------------------------------------
# 5. Continuous Monitoring Service
# ---------------------------------------------------------------------------


class ContinuousMonitoringService:
    """Orchestrates the full CRM pipeline without performing repository analysis."""

    def __init__(
        self,
        repository_inspector=None,
        base_dir: Optional[str] = None,
        default_policy: Optional[MonitoringPolicy] = None,
    ) -> None:
        self.repository_inspector = repository_inspector
        self.base_dir = base_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "monitoring",
        )
        self.default_policy = default_policy or ImmediatePolicy()
        self.change_detector = ChangeDetector()
        self.health_trend_engine = HealthTrendEngine()

    # ------------------------------------------------------------------
    # File system helpers
    # ------------------------------------------------------------------

    def _repo_dir(self, repo_name: str) -> str:
        safe = repo_name.replace("/", "_").replace("\\", "_")
        return os.path.join(self.base_dir, safe)

    def _runs_dir(self, repo_name: str) -> str:
        path = os.path.join(self._repo_dir(repo_name), "runs")
        os.makedirs(path, exist_ok=True)
        return path

    def _trends_dir(self, repo_name: str) -> str:
        path = os.path.join(self._repo_dir(repo_name), "trends")
        os.makedirs(path, exist_ok=True)
        return path

    def _save_run(self, run: MonitoringRun) -> None:
        runs_dir = self._runs_dir(run.repository)
        ts_path = os.path.join(runs_dir, f"{int(run.timestamp)}_{run.id}.json")
        latest_path = os.path.join(runs_dir, "latest.json")
        payload = run.model_dump()
        for path in (ts_path, latest_path):
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)

    def _save_trend(self, repo_name: str, trend: RepositoryHealthTrend) -> None:
        trends_dir = self._trends_dir(repo_name)
        with open(os.path.join(trends_dir, "latest.json"), "w", encoding="utf-8") as fh:
            json.dump(trend.model_dump(), fh, indent=2)

    def _load_run(self, path: str) -> Optional[MonitoringRun]:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return MonitoringRun.model_validate(json.load(fh))
        except Exception as exc:
            logger.warning("Failed to load monitoring run from %s: %s", path, exc)
            return None

    def _load_report(self, report_path: str) -> Optional[Dict[str, Any]]:
        """Loads a persisted InspectionReport without duplicating its findings."""
        try:
            with open(report_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def trigger(
        self,
        repo_name: str,
        twin_data: Dict[str, Any],
        knowledge_graph_data: Dict[str, Any],
        memory_context: Optional[Dict[str, Any]] = None,
        repository_event: Optional[Dict[str, Any]] = None,
        policy: Optional[MonitoringPolicy] = None,
        inspection_policy: str = "default",
    ) -> MonitoringRun:
        """Runs the full CRM pipeline for one repository."""
        start_ts = time.time()
        run_id = str(uuid.uuid4())
        active_policy = policy or self.default_policy

        event = repository_event or {"trigger": "manual"}
        event.setdefault("trigger", "manual")

        # Resolve last run for change detection
        last_run = self.load_latest_run(repo_name)
        if last_run and "last_run_timestamp" not in event:
            event["last_run_timestamp"] = last_run.timestamp

        # 1. Change detection
        change_summary = self.change_detector.detect(event, last_run)
        logger.info("Change summary for '%s': %s", repo_name, change_summary)

        # 2. Policy authorization
        scheduler = MonitoringScheduler(active_policy)
        if not scheduler.is_authorized(event):
            logger.info("Policy '%s' skipped run for '%s'.", active_policy.name, repo_name)
            run = MonitoringRun(
                id=run_id,
                repository=repo_name,
                timestamp=start_ts,
                trigger=event["trigger"],
                policy=active_policy.name,
                inspection_report_path="",
                status="skipped",
                duration_ms=round((time.time() - start_ts) * 1000, 1),
                overall_score=last_run.overall_score if last_run else 100.0,
                metadata={"change_summary": change_summary},
            )
            self._save_run(run)
            return run

        # 3. Invoke Repository Inspector (if available)
        inspection_report_path = ""
        overall_score = 100.0
        finding_counts: Dict[str, int] = {}
        status = "completed"

        if self.repository_inspector is not None:
            try:
                report = self.repository_inspector.inspect(
                    repo_name=repo_name,
                    twin_data=twin_data,
                    knowledge_graph_data=knowledge_graph_data,
                    memory_context=memory_context,
                    policy=inspection_policy,
                )
                overall_score = report.overall_score
                finding_counts = dict(report.statistics.get("by_severity", {}))
                inspection_report_path = os.path.join(
                    self.repository_inspector._get_repo_dir(repo_name),
                    "latest.json",
                )
            except Exception as exc:
                logger.error("Repository Inspector failed: %s", exc, exc_info=True)
                status = "failed"
        else:
            logger.warning("No RepositoryInspector attached; skipping inspection step.")

        duration_ms = round((time.time() - start_ts) * 1000, 1)

        # 4. Persist MonitoringRun (reference to report, no duplicate findings)
        run = MonitoringRun(
            id=run_id,
            repository=repo_name,
            timestamp=start_ts,
            trigger=event["trigger"],
            policy=active_policy.name,
            inspection_report_path=inspection_report_path,
            status=status,
            duration_ms=duration_ms,
            overall_score=overall_score,
            finding_counts=finding_counts,
            metadata={"change_summary": change_summary, "inspection_policy": inspection_policy},
        )
        self._save_run(run)

        # 5. Update health trend
        self._refresh_trend(repo_name)

        return run

    def _refresh_trend(self, repo_name: str) -> None:
        """Regenerates and persists the HealthTrend for a repository."""
        try:
            runs = self.load_history(repo_name)
            inspection_reports = []
            for run in runs:
                if run.inspection_report_path and os.path.exists(run.inspection_report_path):
                    report = self._load_report(run.inspection_report_path)
                    if report:
                        inspection_reports.append(report)

            trend = self.health_trend_engine.build_trend(runs, inspection_reports)
            if trend.repository:
                self._save_trend(repo_name, trend)
        except Exception as exc:
            logger.error("Failed to refresh health trend: %s", exc)

    def load_latest_run(self, repo_name: str) -> Optional[MonitoringRun]:
        latest_path = os.path.join(self._runs_dir(repo_name), "latest.json")
        if not os.path.exists(latest_path):
            return None
        return self._load_run(latest_path)

    def load_history(self, repo_name: str, limit: int = 50) -> List[MonitoringRun]:
        runs_dir = self._runs_dir(repo_name)
        files = sorted(
            [
                os.path.join(runs_dir, f)
                for f in os.listdir(runs_dir)
                if f.endswith(".json") and f != "latest.json"
            ]
        )[-limit:]
        runs = [self._load_run(f) for f in files]
        return [r for r in runs if r is not None]

    def load_trend(self, repo_name: str) -> Optional[RepositoryHealthTrend]:
        trend_path = os.path.join(self._trends_dir(repo_name), "latest.json")
        if not os.path.exists(trend_path):
            return None
        try:
            with open(trend_path, "r", encoding="utf-8") as fh:
                return RepositoryHealthTrend.model_validate(json.load(fh))
        except Exception as exc:
            logger.error("Failed to load trend: %s", exc)
            return None

    def get_status(self, repo_name: str) -> MonitoringStatus:
        runs = self.load_history(repo_name)
        latest = self.load_latest_run(repo_name)
        trend = self.load_trend(repo_name)
        return MonitoringStatus(
            repository=repo_name,
            total_runs=len(runs),
            last_run_timestamp=latest.timestamp if latest else None,
            last_run_status=latest.status if latest else None,
            last_overall_score=latest.overall_score if latest else None,
            current_trend=trend.trend if trend else None,
            active_policy=self.default_policy.name,
        )
