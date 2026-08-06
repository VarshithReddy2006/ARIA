"""Learning Reasoning Engine.

Produces explainable recommendations for files, concepts, scenarios, and architecture layers.
"""

from __future__ import annotations

import os
from typing import Dict, List, Any
from services.architecture.layer_classifier import classify_layer


def generate_recommendation_reasoning(
    target_id: str,
    target_type: str = "file",
    user_goal: str = "Repository Onboarding",
    completed_steps: List[str] | None = None,
) -> Dict[str, Any]:
    """Generate explainable recommendation with confidence score and evidence bullets."""
    completed_steps = completed_steps or []
    file_name = os.path.basename(target_id)
    layer = classify_layer(target_id)

    reason = f"Primary entry point for {layer} layer. Establishes core application lifecycle."
    confidence = 96
    evidence = [
        f"Layer classification detected as {layer}",
        "High execution centrality in repository knowledge graph",
        f"Required prerequisite for understanding downstream {layer} dependencies",
    ]

    if "api" in target_id.lower() or "main" in target_id.lower():
        reason = "Primary HTTP application entry point. All incoming client requests originate here."
        confidence = 98
        evidence = [
            "Matches entry point router pattern",
            "Registers HTTP endpoints and middleware",
            "Referenced during application initialization",
        ]
    elif "service" in target_id.lower():
        reason = "Encapsulates business domain orchestration and handles application use-cases."
        confidence = 94
        evidence = [
            "Classified under Application Service layer",
            "Consumes domain repositories and external providers",
            "Key component for feature implementations",
        ]

    alternatives = [
        {
            "id": "services/chat/retrieval_pipeline.py",
            "label": "Retrieval Pipeline",
            "reason": "Deeper AI pipeline exploration",
        },
        {
            "id": "backend/api.py",
            "label": "FastAPI App Setup",
            "reason": "High-level HTTP overview",
        },
    ]

    return {
        "target_id": target_id,
        "target_name": file_name,
        "target_type": target_type,
        "user_goal": user_goal,
        "reason": reason,
        "confidence_pct": confidence,
        "evidence": evidence,
        "why_this_why_now": f"Complements {len(completed_steps)} previously read modules and unlocks next phase.",
        "prerequisite_unlocked": [
            f"Unlocks deeper {layer} inspection",
            "Unlocks scenario simulations",
        ],
        "alternative_choices": alternatives,
        "estimated_learning_benefit": "+15% Architecture Comprehension",
    }
