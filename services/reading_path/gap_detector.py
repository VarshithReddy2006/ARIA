"""Knowledge Gap Detection & Recovery Subsystem.

Identifies missing concepts, skipped prerequisites, weak quiz areas, and incomplete architecture layer coverage.
"""

from __future__ import annotations

from typing import Dict, List, Any


def detect_knowledge_gaps(
    completed_steps: List[str],
    quiz_scores: Dict[str, float] | None = None,
    all_concepts: List[str] | None = None,
) -> Dict[str, Any]:
    """Analyze learning state and detect knowledge gaps with recovery recommendations."""
    quiz_scores = quiz_scores or {}
    all_concepts = all_concepts or ["Authentication", "Routing", "Dependency Injection", "Database", "Caching", "Testing"]

    completed_set = set(completed_steps)
    missing_concepts = []

    if not any("auth" in s.lower() for s in completed_set):
        missing_concepts.append("Authentication")
    if not any("db" in s.lower() or "repo" in s.lower() for s in completed_set):
        missing_concepts.append("Database")
    if not any("test" in s.lower() for s in completed_set):
        missing_concepts.append("Testing")

    weak_areas = []
    for quiz_id, score in quiz_scores.items():
        if score < 60.0:
            weak_areas.append({"quiz_id": quiz_id, "score": score, "topic": "Architecture Boundaries"})

    recovery_journeys = []
    if missing_concepts:
        recovery_journeys.append({
            "recovery_id": "rec-1",
            "title": f"Bridge {missing_concepts[0]} Knowledge Gap",
            "reason": f"No files covering '{missing_concepts[0]}' have been explored yet.",
            "recommended_steps": [
                "services/db/repository.py" if missing_concepts[0] == "Database" else "backend/api.py"
            ],
            "estimated_minutes": 10,
        })

    return {
        "gap_count": len(missing_concepts) + len(weak_areas),
        "missing_concepts": missing_concepts,
        "weak_quiz_areas": weak_areas,
        "layer_coverage_pct": min(100, round((len(completed_steps) / 10) * 100, 1)),
        "recovery_journeys": recovery_journeys,
    }
