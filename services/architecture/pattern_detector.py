"""Architectural Pattern Detector.

Automatically detects architectural design patterns present in a file or module based on code inspection, path heuristics, and class definitions.
"""

from __future__ import annotations

import re
from typing import List


PATTERNS = [
    "MVC",
    "Clean Architecture",
    "Hexagonal",
    "Repository Pattern",
    "Factory",
    "Adapter",
    "Strategy",
    "Facade",
    "Decorator",
    "Observer",
    "CQRS",
    "Dependency Injection",
    "Singleton",
    "Builder",
    "Command",
    "Pipeline",
    "Middleware",
    "Event Driven",
]


def detect_patterns(path: str, content: str = "", imports: List[str] | None = None) -> List[str]:
    """Detect matching design patterns for a specified file or module."""
    clean_path = path.replace("\\", "/").lower()
    text = (content + " " + " ".join(imports or [])).lower()
    detected = set()

    # Repository Pattern
    if "repository" in clean_path or "repo" in clean_path or "repository" in text:
        detected.add("Repository Pattern")

    # Dependency Injection
    if "inject" in text or "provider" in clean_path or "dependencies.py" in clean_path:
        detected.add("Dependency Injection")

    # Pipeline
    if "pipeline" in clean_path or "pipeline" in text:
        detected.add("Pipeline")

    # Middleware
    if "middleware" in clean_path or "middleware" in text:
        detected.add("Middleware")

    # Factory
    if "factory" in clean_path or "factory" in text or "create_" in text:
        detected.add("Factory")

    # Adapter
    if "adapter" in clean_path or "adapter" in text:
        detected.add("Adapter")

    # Facade
    if "facade" in clean_path or "manager" in clean_path or "orchestrat" in clean_path:
        detected.add("Facade")

    # Strategy
    if "strategy" in clean_path or "policy" in clean_path:
        detected.add("Strategy")

    # Observer / Event Driven
    if "event" in clean_path or "listener" in text or "subscriber" in text or "emitter" in text:
        detected.add("Event Driven")
        detected.add("Observer")

    # Singleton
    if "singleton" in text or "_instance" in text or "get_instance" in text:
        detected.add("Singleton")

    # Command
    if "command" in clean_path or "command" in text or "execut" in text:
        detected.add("Command")

    # Builder
    if "builder" in clean_path or "builder" in text:
        detected.add("Builder")

    # Clean Architecture / Hexagonal
    if "domain" in clean_path and "infrastructure" in clean_path:
        detected.add("Clean Architecture")
        detected.add("Hexagonal")

    # MVC
    if any(k in clean_path for k in ("controller", "model", "view")):
        detected.add("MVC")

    if not detected:
        detected.add("Facade")  # default module structural pattern

    return sorted(list(detected))
