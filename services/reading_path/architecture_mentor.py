"""Architecture Mentor Subsystem.

Provides architectural guidance, layer responsibilities, common mistakes, and best practices.
"""

from __future__ import annotations

from typing import Dict, Any


LAYER_GUIDANCE = {
    "Presentation": {
        "purpose": "Exposes UI views and HTTP API router endpoints to clients.",
        "responsibilities": [
            "Input validation",
            "HTTP status routing",
            "Request deserialization",
        ],
        "common_mistakes": [
            "Direct database calls inside routers",
            "Embedding business rules in controllers",
        ],
        "best_practices": [
            "Delegate logic to Application Service layer",
            "Use strict DTO schemas",
        ],
        "related_patterns": ["MVC", "Facade"],
    },
    "Application": {
        "purpose": "Orchestrates use-cases and coordinates domain workflow execution.",
        "responsibilities": [
            "Transaction boundary management",
            "Use-case orchestration",
            "Security checks",
        ],
        "common_mistakes": [
            "Coupling directly to database drivers",
            "Leaking domain entities to UI",
        ],
        "best_practices": [
            "Depend on abstraction interfaces",
            "Keep handlers focused on single use-case",
        ],
        "related_patterns": ["Pipeline", "Dependency Injection", "Command"],
    },
    "Domain": {
        "purpose": "Contains pure business logic, entities, value objects, and domain rules.",
        "responsibilities": ["Business rule enforcement", "State invariant validation"],
        "common_mistakes": [
            "Importing UI or framework packages",
            "Adding IO database operations",
        ],
        "best_practices": [
            "Keep domain framework-agnostic",
            "Cover 100% with unit tests",
        ],
        "related_patterns": ["Repository Pattern", "Factory", "Strategy"],
    },
    "Infrastructure": {
        "purpose": "Integrates external systems, databases, cloud services, and third-party APIs.",
        "responsibilities": [
            "Database queries",
            "HTTP client calls",
            "FileSystem operations",
        ],
        "common_mistakes": [
            "Bypassing interface contracts",
            "Exposing connection objects",
        ],
        "best_practices": [
            "Implement domain interface ports",
            "Handle retry and timeout resiliency",
        ],
        "related_patterns": ["Adapter", "Singleton"],
    },
}


def get_layer_guidance(layer: str) -> Dict[str, Any]:
    """Return Architecture Mentor guidance for a specific layer."""
    return LAYER_GUIDANCE.get(
        layer,
        {
            "purpose": f"Coordinates logic and module interaction within the {layer} layer.",
            "responsibilities": ["Module interaction", "Code organization"],
            "common_mistakes": ["High coupling across layers"],
            "best_practices": ["Follow single-responsibility principle"],
            "related_patterns": ["Module"],
        },
    )
