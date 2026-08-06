"""Architecture Intelligence v2 Test Suite.

Verifies:
  1. Advanced Metrics Engine (Instability, Distance from Main Sequence, MI, Complexity, Ca, Ce).
  2. Architecture Quality Engine (0-100 score, subscores, quality badges).
  3. Tarjan SCC Cycle Detector (Strongly Connected Components, breakpoint recommendations).
  4. ArchUnit Rule Engine (Layer boundary enforcement, violation reports).
  5. Impact Engine & Shortest Path Explorer (Blast radius, BFS shortest path).
  6. FastAPI endpoints return HTTP 200 with grounded data payloads.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from services.architecture.metrics_engine import compute_metrics
from services.architecture.quality_engine import compute_quality_score
from services.architecture.cycle_detector import detect_cycles
from services.architecture.rules import evaluate_rules
from services.architecture.impact_engine import find_shortest_path
from backend.api import app

client = TestClient(app)


def test_metrics_engine():
    """Verify advanced software metrics computation."""
    content = """
    class ServiceManager:
        def process(self, item):
            if item:
                for x in item:
                    if x > 0:
                        return x
            return None
    """
    metrics = compute_metrics(
        "services/service.py",
        content=content,
        depends_on=["models/schema.py", "utils/helper.py"],
        imported_by=["api/router.py"],
    )

    assert metrics["fan_in"] == 1
    assert metrics["fan_out"] == 2
    assert metrics["instability"] == 0.667
    assert metrics["cyclomatic_complexity"] >= 3
    assert 0 <= metrics["maintainability_index"] <= 100
    assert metrics["lines_of_code"] > 0


def test_quality_engine():
    """Verify Architecture Quality score (0-100) and subscores."""
    node_metrics = [
        {
            "maintainability_index": 90,
            "instability": 0.3,
            "cyclomatic_complexity": 3,
            "fan_in": 5,
            "fan_out": 2,
        },
        {
            "maintainability_index": 85,
            "instability": 0.4,
            "cyclomatic_complexity": 4,
            "fan_in": 2,
            "fan_out": 3,
        },
    ]

    res = compute_quality_score(node_metrics, cycle_count=0, violation_count=0)
    assert 0 <= res["overall_score"] <= 100
    assert res["badge"] in ("EXCELLENT", "GOOD", "NEEDS_ATTENTION", "CRITICAL")
    assert "layering" in res["subscores"]
    assert "coupling" in res["subscores"]
    assert "maintainability" in res["subscores"]


def test_tarjan_cycle_detector():
    """Verify Tarjan SCC cycle detection and breakpoint suggestions."""
    edges = [
        {"source": "mod_a.py", "target": "mod_b.py"},
        {"source": "mod_b.py", "target": "mod_c.py"},
        {"source": "mod_c.py", "target": "mod_a.py"},  # Cycle: A -> B -> C -> A
        {"source": "mod_c.py", "target": "mod_d.py"},
    ]

    res = detect_cycles(edges)
    assert res["cycle_count"] == 1
    assert len(res["cycle_groups"]) == 1
    assert set(res["cycle_groups"][0]["nodes"]) == {"mod_a.py", "mod_b.py", "mod_c.py"}
    assert len(res["breakpoint_suggestions"]) >= 1


def test_archunit_rule_engine():
    """Verify ArchUnit-style layer boundary rule evaluation."""
    edges = [
        {
            "source": "models/domain_entity.py",
            "target": "frontend/views/page.tsx",
        },  # Domain -> Presentation (Violation)
        {
            "source": "frontend/views/page.tsx",
            "target": "services/db/repository.py",
        },  # Presentation -> Data (Violation)
    ]

    res = evaluate_rules(edges)
    assert res["violation_count"] >= 2
    assert res["critical_count"] >= 1
    assert any(v["rule_id"] == "ARCH-001" for v in res["violations"])


def test_shortest_path_explorer():
    """Verify shortest path BFS tracing between Node A and Node B."""
    edges = [
        {"source": "router.py", "target": "service.py"},
        {"source": "service.py", "target": "repository.py"},
        {"source": "repository.py", "target": "db.py"},
    ]

    res = find_shortest_path("router.py", "db.py", edges)
    assert res["distance"] == 3
    assert res["path_nodes"] == ["router.py", "service.py", "repository.py", "db.py"]
    assert res["cross_layer_transitions"] > 0


def test_api_quality_endpoint():
    """Verify GET /api/architecture/{owner}/{repo}/quality."""
    resp = client.get(
        "/api/architecture/VarshithReddy2006/Repo-Intelligence-Agent/quality"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "overall_score" in data
    assert "badge" in data
    assert "subscores" in data


def test_api_cycles_endpoint():
    """Verify GET /api/architecture/{owner}/{repo}/cycles."""
    resp = client.get(
        "/api/architecture/VarshithReddy2006/Repo-Intelligence-Agent/cycles"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "cycle_count" in data


def test_api_rules_violations_endpoint():
    """Verify GET /api/architecture/{owner}/{repo}/rules/violations."""
    resp = client.get(
        "/api/architecture/VarshithReddy2006/Repo-Intelligence-Agent/rules/violations"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "violation_count" in data


def test_api_dependency_path_endpoint():
    """Verify GET /api/architecture/{owner}/{repo}/path."""
    resp = client.get(
        "/api/architecture/VarshithReddy2006/Repo-Intelligence-Agent/path?source=services/chat/api.py&target=services/chat/retrieval.py"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "distance" in data
