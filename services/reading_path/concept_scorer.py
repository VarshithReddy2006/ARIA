"""Concept Importance & Priority Scorer.

Computes importance score, learning difficulty, repository coverage %, and execution frequency for concepts.
"""

from __future__ import annotations

from typing import Dict, Any


def score_concept(
    concept: str,
    file_count: int,
    total_files: int = 20,
) -> Dict[str, Any]:
    """Score importance and difficulty for a concept entity."""
    coverage_pct = min(100.0, round((file_count / max(total_files, 1)) * 100, 1))

    importance_score = min(100, int(50 + coverage_pct * 0.5))
    difficulty = 2
    if concept in ("Dependency Injection", "Caching", "Architecture"):
        difficulty = 4
    elif concept in ("Authentication", "Database"):
        difficulty = 3

    return {
        "concept": concept,
        "importance_score": importance_score,
        "learning_difficulty": difficulty,
        "dependency_count": max(1, file_count),
        "repository_coverage_pct": coverage_pct,
        "execution_frequency": "High" if importance_score > 75 else "Medium",
        "architecture_impact": "Critical" if importance_score > 80 else "Moderate",
        "priority": "P0" if importance_score > 85 else "P1",
    }
