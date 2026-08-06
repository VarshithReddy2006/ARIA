"""Checkpoint Engine Subsystem.

Groups steps into milestone checkpoints with summary cards and concept badges.
"""

from __future__ import annotations

from typing import Dict, List, Any


def build_milestone_checkpoints(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group journey steps into milestone checkpoints every 3 files."""
    checkpoints = []
    chunk_size = 3

    for i in range(0, len(steps), chunk_size):
        chunk = steps[i : i + chunk_size]
        cp_num = (i // chunk_size) + 1
        concepts = set()

        for s in chunk:
            concepts.update(s.get("patterns", []))
            concepts.add(s.get("layer", "Domain"))

        checkpoints.append(
            {
                "checkpoint_id": f"cp-{cp_num}",
                "checkpoint_number": cp_num,
                "title": f"Milestone {cp_num}: {chunk[0]['phase'] if chunk else 'Architecture Overview'}",
                "file_count": len(chunk),
                "step_ids": [s["step_id"] for s in chunk],
                "concepts_learned": list(concepts),
                "summary": f"Completed inspection of {len(chunk)} key modules.",
            }
        )

    return checkpoints
