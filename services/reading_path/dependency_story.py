"""Dependency Story & Execution Scenario Generator.

Converts static import lists into explainable human-readable narratives and request execution scenarios.
"""

from __future__ import annotations

import os
from typing import Dict, List, Any


def generate_dependency_story(file_path: str, depends_on: List[str], imported_by: List[str]) -> Dict[str, Any]:
    """Generate human-readable narrative explaining file dependencies."""
    file_name = os.path.basename(file_path)

    narrative_steps = [
        f"1. '{file_name}' acts as a core module entry point.",
    ]

    if depends_on:
        narrative_steps.append(
            f"2. Initializes and consumes {len(depends_on)} downstream modules ({', '.join(os.path.basename(d) for d in depends_on[:3])})."
        )
    if imported_by:
        narrative_steps.append(
            f"3. Supplies services and interface handlers to {len(imported_by)} upstream consumers ({', '.join(os.path.basename(i) for i in imported_by[:3])})."
        )

    return {
        "file_path": file_path,
        "story_title": f"Dependency Interaction Story for {file_name}",
        "narrative": " → ".join(narrative_steps),
        "steps": narrative_steps,
    }


def generate_execution_scenarios(owner_repo: str) -> List[Dict[str, Any]]:
    """Return available interactive request lifecycle scenarios for simulation."""
    return [
        {
            "scenario_id": "scen-login",
            "title": "Authentication Lifecycle (POST /api/login)",
            "description": "Simulates request flow from client browser through FastAPI router, JWT validation service, user repository, to database query.",
            "flow": [
                {"step": 1, "component": "Client Browser", "layer": "Client", "action": "Sends POST /login payload with credentials"},
                {"step": 2, "component": "backend/api.py", "layer": "Presentation", "action": "Parses HTTP JSON request & validates Pydantic schema"},
                {"step": 3, "component": "services/auth/service.py", "layer": "Application", "action": "Verifies bcrypt password hash & generates JWT token"},
                {"step": 4, "component": "services/db/repository.py", "layer": "Data", "action": "Executes SELECT user query on Database"},
                {"step": 5, "component": "HTTP 200 Response", "layer": "Client", "action": "Returns bearer token & set-cookie header to browser"},
            ],
            "recommended_reason": "Authentication concepts remain incomplete. Recommended to master auth security lifecycle.",
        },
        {
            "scenario_id": "scen-retrieval",
            "title": "Repository Chat Retrieval Pipeline",
            "description": "Traces query flow from chat UI through retrieval pipeline, vector embedding search, and DeepSeek provider fallback.",
            "flow": [
                {"step": 1, "component": "ChatInterface.tsx", "layer": "Presentation", "action": "Sends user query message over SSE stream"},
                {"step": 2, "component": "services/chat/retrieval_pipeline.py", "layer": "Application", "action": "Runs hybrid RAG search & explicit entity extraction"},
                {"step": 3, "component": "services/llm/deepseek_provider.py", "layer": "Infrastructure", "action": "Streams completion tokens back to client"},
            ],
            "recommended_reason": "Explore core AI retrieval pipeline execution path.",
        },
    ]
