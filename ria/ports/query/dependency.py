"""Dependency Analysis Port Definition."""

from typing import Protocol, Any


class DependencyAnalysisPort(Protocol):
    """Port interface for dependency analysis."""

    def analyze_dependencies(self, target: Any) -> Any: ...
