"""Unit tests for the Engineering Memory models, policies, services, and REST router."""

import sys
import os
import tempfile
from unittest.mock import patch
from fastapi.testclient import TestClient

# Ensure root directory is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.api import app
from models.memory import (
    RepositorySnapshot,
    RepositoryEvent,
    RepositoryTimeline,
    TrendMetric,
)
from services.memory_service import (
    RecentHistoryPolicy,
    DependencyHistoryPolicy,
    TimelineBuilder,
    TrendAnalyzer,
    EngineeringMemoryService,
)

client = TestClient(app)


def test_memory_models() -> None:
    """Verifies that Engineering Memory Pydantic models validate successfully."""
    snap = RepositorySnapshot(
        snapshot_id="test_repo_c1",
        repository="owner/repo",
        timestamp=1000.0,
        commit_sha="c1",
        branch="main",
        analysis_version="2.0",
        digital_twin_reference="twin::c1",
        knowledge_graph_reference="kg::c1",
        health_reference="health::c1",
        metrics={"health_score": 95.0, "complexity": 2.0},
    )

    ev = RepositoryEvent(
        event_id="e1",
        repository="owner/repo",
        timestamp=1005.0,
        commit_sha="c1",
        event_type="FileAdded",
        affected_entity="src/main.py",
        severity="info",
    )

    timeline = RepositoryTimeline(repository="owner/repo", snapshots=[snap], events=[ev])
    assert timeline.repository == "owner/repo"
    assert len(timeline.snapshots) == 1
    assert timeline.events[0].event_type == "FileAdded"


def test_timeline_builder_and_trends() -> None:
    """Verifies chronological timeline compilation and trend analytics calculations."""
    repo = "owner/repo"
    snap1 = RepositorySnapshot(
        snapshot_id="r_c1",
        repository=repo,
        timestamp=1000.0,
        commit_sha="c1",
        branch="main",
        analysis_version="2.0",
        digital_twin_reference="twin::c1",
        knowledge_graph_reference="kg::c1",
        health_reference="health::c1",
        metrics={"health_score": 90.0, "complexity": 2.0},
    )
    snap2 = RepositorySnapshot(
        snapshot_id="r_c2",
        repository=repo,
        timestamp=2000.0,
        commit_sha="c2",
        branch="main",
        analysis_version="2.0",
        digital_twin_reference="twin::c2",
        knowledge_graph_reference="kg::c2",
        health_reference="health::c2",
        metrics={"health_score": 95.0, "complexity": 4.0},
    )

    ev = RepositoryEvent(
        event_id="e1",
        repository=repo,
        timestamp=1500.0,
        commit_sha="c2",
        event_type="ComplexityChanged",
        affected_entity="complexity",
    )

    # 1. TimelineBuilder
    builder = TimelineBuilder()
    timeline = builder.build_timeline(repo, [snap2, snap1], [ev])
    # Chronological sort order verification
    assert timeline.snapshots[0].commit_sha == "c1"
    assert timeline.snapshots[1].commit_sha == "c2"
    assert len(timeline.events) == 1

    # 2. TrendAnalyzer
    analyzer = TrendAnalyzer()
    trends = analyzer.analyze_trends([snap1, snap2])
    # Complexity trend key verification (should show increasing direction)
    complexity_trend = next(t for t in trends if t.metric_name == "complexity")
    assert complexity_trend.direction == "Increasing"
    assert complexity_trend.confidence > 0.0


def test_memory_policies() -> None:
    """Verifies that scoped memory policies prune history context as expected."""
    repo = "owner/repo"
    snaps = [
        RepositorySnapshot(
            snapshot_id=f"r_{i}",
            repository=repo,
            timestamp=float(i * 100),
            commit_sha=f"c{i}",
            branch="main",
            analysis_version="2.0",
            digital_twin_reference="twin",
            knowledge_graph_reference="kg",
            health_reference="health",
            metrics={},
        )
        for i in range(1, 10)
    ]

    events = [
        RepositoryEvent(
            event_id="e1",
            repository=repo,
            timestamp=150.0,
            commit_sha="c1",
            event_type="DependencyAdded",
            affected_entity="requests",
        ),
        RepositoryEvent(
            event_id="e2",
            repository=repo,
            timestamp=250.0,
            commit_sha="c2",
            event_type="ArchitectureChanged",
            affected_entity="src/utils.py",
        ),
    ]

    # RecentHistoryPolicy (limit 3)
    recent_policy = RecentHistoryPolicy(limit=3)
    filtered_snaps, filtered_events = recent_policy.filter_context(snaps, events)
    assert len(filtered_snaps) == 3
    # Timestamps should map to latest: 700, 800, 900
    assert filtered_snaps[0].timestamp == 700.0

    # DependencyHistoryPolicy
    dep_policy = DependencyHistoryPolicy()
    _, dep_events = dep_policy.filter_context(snaps, events)
    assert len(dep_events) == 1
    assert dep_events[0].event_type == "DependencyAdded"


def test_memory_service_storage() -> None:
    """Verifies file-system read/write operations of Engineering Memory Service."""
    repo = "owner/repo"
    with tempfile.TemporaryDirectory() as tmpdir:
        service = EngineeringMemoryService(base_dir=tmpdir)
        
        # Verify empty load
        assert service.load_snapshot(repo, "c1") is None
        
        # Save snapshot
        snap = RepositorySnapshot(
            snapshot_id="r_c1",
            repository=repo,
            timestamp=1000.0,
            commit_sha="c1",
            branch="main",
            analysis_version="2.0",
            digital_twin_reference="twin",
            knowledge_graph_reference="kg",
            health_reference="health",
            metrics={"health_score": 90.0},
        )
        service.save_snapshot(snap)
        
        # Load snapshot
        loaded = service.load_snapshot(repo, "c1")
        assert loaded is not None
        assert loaded.commit_sha == "c1"
        assert loaded.metrics["health_score"] == 90.0

        # Save and load events
        ev = RepositoryEvent(
            event_id="e1",
            repository=repo,
            timestamp=1005.0,
            commit_sha="c1",
            event_type="FileAdded",
            affected_entity="src/main.py",
        )
        service.save_events(repo, "c1", [ev])
        loaded_events = service.load_events(repo, "c1")
        assert len(loaded_events) == 1
        assert loaded_events[0].event_type == "FileAdded"


def test_memory_router_endpoints() -> None:
    """Verifies HTTP GET endpoints of the REST router return expected schemas."""
    repo_name = "test-owner/test-repo"

    with patch("backend.routers.memory.engineering_memory_service") as mock_service:
        # Mock snapshots
        snap = RepositorySnapshot(
            snapshot_id="r_c1",
            repository=repo_name,
            timestamp=1000.0,
            commit_sha="c1",
            branch="main",
            analysis_version="2.0",
            digital_twin_reference="twin",
            knowledge_graph_reference="kg",
            health_reference="health",
            metrics={"health_score": 95.0},
        )
        mock_service.navigator.get_history.return_value = [snap]

        timeline = RepositoryTimeline(repository=repo_name, snapshots=[snap], events=[])
        mock_service.navigator.get_timeline.return_value = timeline
        mock_service.navigator.get_trends.return_value = [
            TrendMetric(metric_name="health_score", direction="Stable", velocity="Low", volatility="Low", confidence=1.0)
        ]
        
        # Test GET snapshots
        response = client.get("/api/repositories/test-owner/test-repo/memory/snapshots")
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["commit_sha"] == "c1"

        # Test GET timeline
        response = client.get("/api/repositories/test-owner/test-repo/memory/timeline")
        assert response.status_code == 200
        assert response.json()["repository"] == repo_name

        # Test GET trends
        response = client.get("/api/repositories/test-owner/test-repo/memory/trends")
        assert response.status_code == 200
        assert response.json()[0]["metric_name"] == "health_score"
