"""Architecture Quality Engine.

Computes repository-wide 0–100 Architecture Score and subscores:
  - Layering (0–100)
  - Coupling (0–100)
  - Cohesion (0–100)
  - Complexity (0–100)
  - Maintainability (0–100)
  - Dependency Health (0–100)
  - Testability (0–100)
"""

from __future__ import annotations

from typing import Dict, Any, List


def compute_quality_score(
    node_metrics_list: List[Dict[str, Any]],
    cycle_count: int = 0,
    violation_count: int = 0,
) -> Dict[str, Any]:
    """Compute repository-wide Architecture Score (0-100) and subscores."""
    if not node_metrics_list:
        return {
            "overall_score": 85,
            "badge": "GOOD",
            "subscores": {
                "layering": 85,
                "coupling": 80,
                "cohesion": 85,
                "complexity": 80,
                "maintainability": 85,
                "dependency_health": 90,
                "testability": 85,
            },
        }

    avg_mi = sum(m.get("maintainability_index", 80) for m in node_metrics_list) / len(
        node_metrics_list
    )
    avg_instability = sum(m.get("instability", 0.5) for m in node_metrics_list) / len(
        node_metrics_list
    )
    avg_complexity = sum(
        m.get("cyclomatic_complexity", 5) for m in node_metrics_list
    ) / len(node_metrics_list)
    avg_ca_ce = sum(
        m.get("fan_in", 0) + m.get("fan_out", 0) for m in node_metrics_list
    ) / len(node_metrics_list)

    # Subscore calculations
    layering = max(0, min(100, int(95 - (violation_count * 5))))
    coupling = max(0, min(100, int(90 - (avg_ca_ce * 3))))
    cohesion = max(0, min(100, int(90 - (avg_instability * 20))))
    complexity = max(0, min(100, int(95 - (avg_complexity * 2))))
    maintainability = max(0, min(100, int(avg_mi)))
    dependency_health = max(0, min(100, int(100 - (cycle_count * 15))))
    testability = max(0, min(100, int(85 + (avg_mi * 0.15) - (avg_complexity * 1.5))))

    subscores = {
        "layering": layering,
        "coupling": coupling,
        "cohesion": cohesion,
        "complexity": complexity,
        "maintainability": maintainability,
        "dependency_health": dependency_health,
        "testability": testability,
    }

    overall = int(sum(subscores.values()) / len(subscores))

    badge = "EXCELLENT"
    if overall >= 90:
        badge = "EXCELLENT"
    elif overall >= 80:
        badge = "GOOD"
    elif overall >= 60:
        badge = "NEEDS_ATTENTION"
    else:
        badge = "CRITICAL"

    return {
        "overall_score": overall,
        "badge": badge,
        "subscores": subscores,
    }
