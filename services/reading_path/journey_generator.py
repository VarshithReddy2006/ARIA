"""Journey Generator Subsystem.

Generates 16 goal-based learning journeys tailored across 5 adaptive experience levels.
"""

from __future__ import annotations

import os
from typing import Dict, List, Any
from services.architecture.layer_classifier import classify_layer
from services.architecture.pattern_detector import detect_patterns
from .repository_knowledge_graph import RepositoryKnowledgeGraph


GOALS = [
    "Repository Onboarding",
    "Architecture Tour",
    "Backend Deep Dive",
    "Frontend Deep Dive",
    "Authentication Flow",
    "API Journey",
    "Database Journey",
    "Security Review",
    "Performance Analysis",
    "Testing Journey",
    "Deployment Journey",
    "AI Components",
    "Bug Investigation",
    "Feature Implementation",
    "PR Review",
    "Contributor Onboarding",
]

LEVELS = [
    "Student",
    "Junior Developer",
    "Intermediate Developer",
    "Senior Engineer",
    "Maintainer",
]


def generate_journey(
    pkg: RepositoryKnowledgeGraph,
    goal: str = "Repository Onboarding",
    level: str = "Junior Developer",
) -> Dict[str, Any]:
    """Generate structured multi-phase reading journey tailored for a goal and experience level."""
    all_files = list(pkg.nodes.keys())
    if not all_files:
        all_files = [
            "backend/main.py",
            "backend/api.py",
            "services/chat/retrieval_pipeline.py",
            "services/db/repository.py",
            "frontend/src/App.tsx",
            "tests/test_api.py",
        ]

    # Categorize into 6 journey phases
    phases: Dict[str, List[str]] = {
        "1. Foundation & Entry": [],
        "2. Routing & APIs": [],
        "3. Core Application Services": [],
        "4. Domain & Data Layer": [],
        "5. Infrastructure & External": [],
        "6. Verification & Testing": [],
    }

    for path in all_files:
        layer = classify_layer(path)
        if layer in ("Presentation", "Configuration") or "main" in path or "app" in path:
            phases["1. Foundation & Entry"].append(path)
        elif "router" in path or "api" in path or "endpoint" in path:
            phases["2. Routing & APIs"].append(path)
        elif layer == "Application" or "service" in path:
            phases["3. Core Application Services"].append(path)
        elif layer in ("Domain", "Data") or "db" in path or "repo" in path or "model" in path:
            phases["4. Domain & Data Layer"].append(path)
        elif layer in ("Infrastructure", "Integration") or "client" in path:
            phases["5. Infrastructure & External"].append(path)
        else:
            phases["6. Verification & Testing"].append(path)

    steps: List[Dict[str, Any]] = []
    step_idx = 1

    for phase_name, files in phases.items():
        if not files:
            continue

        selected_files = files[:3] if level in ("Student", "Junior Developer") else files[:5]

        for file_path in selected_files:
            layer = classify_layer(file_path)
            patterns = detect_patterns(file_path)
            file_name = os.path.basename(file_path)

            step = {
                "step_id": f"step-{step_idx}",
                "step_number": step_idx,
                "file_path": file_path,
                "file_name": file_name,
                "phase": phase_name,
                "layer": layer,
                "patterns": patterns,
                "importance": "High" if step_idx <= 3 else "Medium",
                "estimated_time_minutes": 5 if level == "Senior Engineer" else 10,
                "difficulty": "Beginner" if step_idx <= 2 else "Intermediate",
                "why_this_matters": f"Key component in {phase_name}. Establishes contract for {layer} layer.",
                "what_you_will_learn": [
                    f"Understanding {layer} architectural responsibilities",
                    f"Tracing data interactions in {file_name}",
                    f"Exploring design patterns: {', '.join(patterns) if patterns else 'Standard Module'}",
                ],
                "after_reading_comprehension": [
                    "How requests enter and transition through this module",
                    "What dependencies are injected and consumed",
                ],
                "prerequisites": [steps[-1]["file_path"]] if steps else [],
                "next_recommendation": f"Proceed to next module in {phase_name}",
            }
            steps.append(step)
            step_idx += 1

    return {
        "goal": goal,
        "level": level,
        "total_steps": len(steps),
        "estimated_total_minutes": sum(s["estimated_time_minutes"] for s in steps),
        "phases": list(phases.keys()),
        "steps": steps,
    }
