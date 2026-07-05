"""Engineering Memory Services.

Implements TimelineBuilder, TrendAnalyzer, MemoryNavigator, MemoryPolicy strategies,
and the main EngineeringMemoryService.
"""

from __future__ import annotations

import os
import json
import uuid
import time
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from models.memory import (
    RepositorySnapshot,
    RepositoryEvent,
    RepositoryTimeline,
    TrendMetric,
    MemoryContext,
    ComparisonResult,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Memory Policy Strategy Pattern
# ---------------------------------------------------------------------------

class MemoryPolicy(ABC):
    """Abstract strategy for context pruning and bounding."""

    @abstractmethod
    def name(self) -> str:
        """Name of the policy strategy."""
        pass

    @abstractmethod
    def filter_context(
        self,
        snapshots: List[RepositorySnapshot],
        events: List[RepositoryEvent],
    ) -> Tuple[List[RepositorySnapshot], List[RepositoryEvent]]:
        """Filters/bounds snapshots and events based on the policy strategy."""
        pass


class RecentHistoryPolicy(MemoryPolicy):
    """Retrieves only the most recent snapshots and chronological events."""

    def __init__(self, limit: int = 5) -> None:
        self.limit = limit

    def name(self) -> str:
        return "recent_history"

    def filter_context(
        self,
        snapshots: List[RepositorySnapshot],
        events: List[RepositoryEvent],
    ) -> Tuple[List[RepositorySnapshot], List[RepositoryEvent]]:
        sorted_snapshots = sorted(snapshots, key=lambda s: s.timestamp)
        bounded_snapshots = sorted_snapshots[-self.limit:]
        
        if not bounded_snapshots:
            return [], []
            
        min_time = bounded_snapshots[0].timestamp
        bounded_events = [e for e in events if e.timestamp >= min_time]
        return bounded_snapshots, bounded_events


class ArchitectureHistoryPolicy(MemoryPolicy):
    """Filters memory to architecture and structural change events."""

    def name(self) -> str:
        return "architecture_history"

    def filter_context(
        self,
        snapshots: List[RepositorySnapshot],
        events: List[RepositoryEvent],
    ) -> Tuple[List[RepositorySnapshot], List[RepositoryEvent]]:
        arch_events = [
            e for e in events
            if e.event_type in ("ArchitectureChanged", "ComplexityChanged", "FileAdded", "FileRemoved")
        ]
        return sorted(snapshots, key=lambda s: s.timestamp), arch_events


class DependencyHistoryPolicy(MemoryPolicy):
    """Filters memory to package and dependency modification events."""

    def name(self) -> str:
        return "dependency_history"

    def filter_context(
        self,
        snapshots: List[RepositorySnapshot],
        events: List[RepositoryEvent],
    ) -> Tuple[List[RepositorySnapshot], List[RepositoryEvent]]:
        dep_events = [
            e for e in events
            if e.event_type in ("DependencyAdded", "DependencyRemoved")
        ]
        return sorted(snapshots, key=lambda s: s.timestamp), dep_events


class ComplianceHistoryPolicy(MemoryPolicy):
    """Filters memory to compliance and licensing warning events."""

    def name(self) -> str:
        return "compliance_history"

    def filter_context(
        self,
        snapshots: List[RepositorySnapshot],
        events: List[RepositoryEvent],
    ) -> Tuple[List[RepositorySnapshot], List[RepositoryEvent]]:
        comp_events = [
            e for e in events
            if e.event_type in ("ComplianceChanged", "HealthChanged")
        ]
        return sorted(snapshots, key=lambda s: s.timestamp), comp_events


# ---------------------------------------------------------------------------
# Timeline Builder
# ---------------------------------------------------------------------------

class TimelineBuilder:
    """Constructs chronological timelines by joining snapshots and event streams."""

    def build_timeline(
        self,
        repository: str,
        snapshots: List[RepositorySnapshot],
        events: List[RepositoryEvent],
    ) -> RepositoryTimeline:
        """Merges lists of snapshots and events in chronological order."""
        sorted_snapshots = sorted(snapshots, key=lambda s: s.timestamp)
        sorted_events = sorted(events, key=lambda e: e.timestamp)
        return RepositoryTimeline(
            repository=repository,
            snapshots=sorted_snapshots,
            events=sorted_events,
        )


# ---------------------------------------------------------------------------
# Trend Analyzer
# ---------------------------------------------------------------------------

class TrendAnalyzer:
    """Performs mathematical trend calculations over historic repository metrics."""

    def analyze_trends(self, snapshots: List[RepositorySnapshot]) -> List[TrendMetric]:
        """Calculates trend direction, velocity, volatility, and confidence."""
        if len(snapshots) < 2:
            # Need at least two data points to establish a trend direction
            return [
                TrendMetric(
                    metric_name="health_score",
                    direction="Stable",
                    velocity="Low",
                    volatility="Low",
                    confidence=1.0,
                ),
                TrendMetric(
                    metric_name="complexity",
                    direction="Stable",
                    velocity="Low",
                    volatility="Low",
                    confidence=1.0,
                ),
            ]

        sorted_snapshots = sorted(snapshots, key=lambda s: s.timestamp)
        timestamps = [s.timestamp for s in sorted_snapshots]

        trends = []
        metrics_keys = ["health_score", "complexity", "dependency_count", "files_count"]

        for key in metrics_keys:
            values = []
            for s in sorted_snapshots:
                val = s.metrics.get(key, 0)
                # handle float/int conversions safely
                values.append(float(val) if val is not None else 0.0)

            # Calculate direction & velocity (simplistic linear slope)
            y_diff = values[-1] - values[0]
            x_diff = (timestamps[-1] - timestamps[0]) or 1.0
            slope = y_diff / x_diff

            if abs(slope) < 0.0001:
                direction = "Stable"
                velocity = "Low"
            else:
                direction = "Increasing" if slope > 0 else "Decreasing"
                # Velocity bounds
                abs_slope = abs(slope)
                if abs_slope > 1.0:
                    velocity = "High"
                elif abs_slope > 0.1:
                    velocity = "Medium"
                else:
                    velocity = "Low"

            # Volatility (standard deviation of consecutive differences)
            diffs = []
            for i in range(1, len(values)):
                diffs.append(values[i] - values[i - 1])
            
            mean_diff = sum(diffs) / len(diffs)
            variance = sum((d - mean_diff) ** 2 for d in diffs) / len(diffs)
            volatility_val = variance ** 0.5

            if volatility_val > 10.0:
                volatility = "High"
            elif volatility_val > 1.0:
                volatility = "Medium"
            else:
                volatility = "Low"

            # Confidence based on volatility and sample size
            confidence = max(0.0, min(1.0, 1.0 - (volatility_val / (max(values) or 1.0))))
            if len(values) < 3:
                confidence *= 0.7  # penalty for very small sample size

            trends.append(
                TrendMetric(
                    metric_name=key,
                    direction=direction,
                    velocity=velocity,
                    volatility=volatility,
                    confidence=round(confidence, 2),
                )
            )

        return trends


# ---------------------------------------------------------------------------
# Memory Navigator (Historical Query Engine)
# ---------------------------------------------------------------------------

class MemoryNavigator:
    """Query façade navigates history, comparing snapshots/commits and resolving context."""

    def __init__(self, service: EngineeringMemoryService) -> None:
        self.service = service
        self.timeline_builder = TimelineBuilder()
        self.trend_analyzer = TrendAnalyzer()

    def get_snapshot(self, repo_name: str, commit_sha: str) -> Optional[RepositorySnapshot]:
        return self.service.load_snapshot(repo_name, commit_sha)

    def get_history(self, repo_name: str) -> List[RepositorySnapshot]:
        return self.service.load_all_snapshots(repo_name)

    def get_changes(self, repo_name: str) -> List[RepositoryEvent]:
        return self.service.load_all_events(repo_name)

    def get_timeline(self, repo_name: str) -> RepositoryTimeline:
        snapshots = self.get_history(repo_name)
        events = self.get_changes(repo_name)
        return self.timeline_builder.build_timeline(repo_name, snapshots, events)

    def get_trends(self, repo_name: str) -> List[TrendMetric]:
        snapshots = self.get_history(repo_name)
        return self.trend_analyzer.analyze_trends(snapshots)

    def compare_snapshots(
        self,
        prev: RepositorySnapshot,
        curr: RepositorySnapshot,
    ) -> ComparisonResult:
        # Load events between the two timestamps
        events = self.service.load_all_events(curr.repository)
        t_min = min(prev.timestamp, curr.timestamp)
        t_max = max(prev.timestamp, curr.timestamp)
        filtered_events = [e for e in events if t_min <= e.timestamp <= t_max]

        # Deltas
        prev_health = prev.metrics.get("health_score", 100.0) or 100.0
        curr_health = curr.metrics.get("health_score", 100.0) or 100.0
        health_delta = float(curr_health - prev_health)

        prev_deps = prev.metrics.get("dependency_count", 0) or 0
        curr_deps = curr.metrics.get("dependency_count", 0) or 0
        dep_delta = int(curr_deps - prev_deps)

        return ComparisonResult(
            previous_commit=prev.commit_sha,
            current_commit=curr.commit_sha,
            changes=filtered_events,
            health_delta=health_delta,
            dependency_delta=dep_delta,
        )

    def compare_commits(self, repo_name: str, prev_commit: str, curr_commit: str) -> ComparisonResult:
        prev = self.get_snapshot(repo_name, prev_commit)
        curr = self.get_snapshot(repo_name, curr_commit)
        if not prev or not curr:
            raise ValueError(f"Cannot compare commits. Snapshots for commits '{prev_commit}' or '{curr_commit}' not found.")
        return self.compare_snapshots(prev, curr)

    def get_memory_context(self, repo_name: str, policy: MemoryPolicy) -> MemoryContext:
        snapshots = self.get_history(repo_name)
        events = self.get_changes(repo_name)

        filtered_snapshots, filtered_events = policy.filter_context(snapshots, events)
        timeline = self.timeline_builder.build_timeline(repo_name, filtered_snapshots, filtered_events)
        trends = self.trend_analyzer.analyze_trends(filtered_snapshots)

        return MemoryContext(
            policy=policy.name(),
            snapshots=filtered_snapshots,
            timeline=timeline,
            trend_metrics=trends,
        )


# ---------------------------------------------------------------------------
# Engineering Memory Service
# ---------------------------------------------------------------------------

class EngineeringMemoryService:
    """Append-only storage service managing facts-only snapshots and repository event logs."""

    def __init__(self, base_dir: Optional[str] = None) -> None:
        if base_dir is None:
            base_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data",
                "engineering_memory",
            )
        self.base_dir = base_dir
        self.navigator = MemoryNavigator(self)

    def _get_repo_dir(self, repo_name: str, folder: str) -> str:
        safe_repo = repo_name.replace("/", "_").replace("\\", "_")
        path = os.path.join(self.base_dir, safe_repo, folder)
        os.makedirs(path, exist_ok=True)
        return path

    def save_snapshot(self, snapshot: RepositorySnapshot) -> None:
        """Saves a facts-only repository snapshot to disk."""
        path = os.path.join(self._get_repo_dir(snapshot.repository, "snapshots"), f"{snapshot.commit_sha}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(snapshot.model_dump(), fh, indent=2)
        logger.info("Saved Engineering Memory Snapshot: %s", path)

    def load_snapshot(self, repo_name: str, commit_sha: str) -> Optional[RepositorySnapshot]:
        """Loads a repository snapshot associated with a specific commit."""
        path = os.path.join(self._get_repo_dir(repo_name, "snapshots"), f"{commit_sha}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                return RepositorySnapshot.model_validate(data)
        except Exception as exc:
            logger.error("Failed to load snapshot from %s: %s", path, exc)
            return None

    def load_all_snapshots(self, repo_name: str) -> List[RepositorySnapshot]:
        """Retrieves all snapshots chronologically."""
        dir_path = self._get_repo_dir(repo_name, "snapshots")
        snapshots = []
        for entry in os.listdir(dir_path):
            if entry.endswith(".json"):
                commit_sha = entry[:-5]
                snap = self.load_snapshot(repo_name, commit_sha)
                if snap:
                    snapshots.append(snap)
        return sorted(snapshots, key=lambda s: s.timestamp)

    def save_events(self, repo_name: str, commit_sha: str, events: List[RepositoryEvent]) -> None:
        """Saves a batch of events introduced in a commit."""
        path = os.path.join(self._get_repo_dir(repo_name, "events"), f"{commit_sha}.json")
        payload = [e.model_dump() for e in events]
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        logger.info("Saved Engineering Memory Events (%d events): %s", len(events), path)

    def load_events(self, repo_name: str, commit_sha: str) -> List[RepositoryEvent]:
        """Loads events associated with a specific commit."""
        path = os.path.join(self._get_repo_dir(repo_name, "events"), f"{commit_sha}.json")
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                return [RepositoryEvent.model_validate(e) for e in data]
        except Exception as exc:
            logger.error("Failed to load events from %s: %s", path, exc)
            return []

    def load_all_events(self, repo_name: str) -> List[RepositoryEvent]:
        """Retrieves all logged repository events."""
        dir_path = self._get_repo_dir(repo_name, "events")
        events = []
        for entry in os.listdir(dir_path):
            if entry.endswith(".json"):
                commit_sha = entry[:-5]
                events.extend(self.load_events(repo_name, commit_sha))
        return sorted(events, key=lambda e: e.timestamp)

    def create_snapshot(
        self,
        repo_name: str,
        commit_sha: str,
        branch: str,
        twin_data: Dict[str, Any],
        change_set: Optional[Any] = None,
    ) -> RepositorySnapshot:
        """Constructs and persists a facts-only snapshot and its events log."""
        timestamp = time.time()
        
        # Calculate summary metrics
        twin_meta = twin_data.get("metadata", {})
        metrics = {
            "health_score": twin_meta.get("health_score", 100.0),
            "complexity": twin_meta.get("complexity", 1.0),
            "dependency_count": len(twin_data.get("dependencies", {}).get("relationships", [])),
            "files_count": len(twin_data.get("files", [])),
            "symbols_count": len(twin_data.get("symbols", {}).get("declarations", [])),
        }

        snapshot = RepositorySnapshot(
            snapshot_id=f"{repo_name.replace('/', '_')}_{commit_sha}",
            repository=repo_name,
            timestamp=timestamp,
            commit_sha=commit_sha,
            branch=branch,
            analysis_version="2.0",
            digital_twin_reference=f"twin::{repo_name}::{commit_sha}",
            knowledge_graph_reference=f"kg::{repo_name}::{commit_sha}",
            health_reference=f"health::{repo_name}::{commit_sha}",
            metrics=metrics,
        )

        # Log RepositoryEvents if a change set is provided
        events = []
        if change_set:
            # File Changes
            for f in change_set.added:
                events.append(
                    RepositoryEvent(
                        event_id=str(uuid.uuid4()),
                        repository=repo_name,
                        timestamp=timestamp,
                        commit_sha=commit_sha,
                        event_type="FileAdded",
                        affected_entity=f,
                        severity="info",
                    )
                )
            for f in change_set.modified:
                events.append(
                    RepositoryEvent(
                        event_id=str(uuid.uuid4()),
                        repository=repo_name,
                        timestamp=timestamp,
                        commit_sha=commit_sha,
                        event_type="FileModified",
                        affected_entity=f,
                        severity="info",
                    )
                )
            for f in change_set.deleted:
                events.append(
                    RepositoryEvent(
                        event_id=str(uuid.uuid4()),
                        repository=repo_name,
                        timestamp=timestamp,
                        commit_sha=commit_sha,
                        event_type="FileRemoved",
                        affected_entity=f,
                        severity="info",
                    )
                )
        
        # Save snapshot & events
        self.save_snapshot(snapshot)
        self.save_events(repo_name, commit_sha, events)

        return snapshot
