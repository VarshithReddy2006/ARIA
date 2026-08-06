"""Progress & Achievement Tracker.

Tracks completed files, reading streak, learned concepts, architecture coverage %, and achievement badges.
"""

from __future__ import annotations

from typing import Dict, List, Any


def get_user_progress(completed_steps: List[str], total_steps: int = 15) -> Dict[str, Any]:
    """Calculate progress analytics, reading streak, and achievement badges."""
    completed_count = len(completed_steps)
    progress_pct = min(100.0, round((completed_count / max(total_steps, 1)) * 100, 1))

    badges = []
    if completed_count >= 1:
        badges.append({"badge_id": "b1", "name": "Repository Navigator", "description": "Completed first repository step"})
    if completed_count >= 3:
        badges.append({"badge_id": "b2", "name": "Entry Points Mastered", "description": "Mastered application entry points"})
    if completed_count >= 6:
        badges.append({"badge_id": "b3", "name": "Routing & Services Expert", "description": "Explored API routing and service orchestration"})
    if completed_count >= 10:
        badges.append({"badge_id": "b4", "name": "Architecture Explorer", "description": "Covered 70%+ of repository layers"})

    return {
        "completed_steps_count": completed_count,
        "total_steps": total_steps,
        "progress_pct": progress_pct,
        "reading_streak_days": min(7, completed_count + 1),
        "concepts_learned_count": completed_count * 2,
        "architecture_coverage_pct": min(100.0, progress_pct * 0.9),
        "unlocked_badges": badges,
    }
