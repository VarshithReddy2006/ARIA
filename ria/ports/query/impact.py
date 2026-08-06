"""Impact Analysis Port Definition."""

from typing import Protocol, Any


class ImpactAnalysisPort(Protocol):
    """Port interface for impact analysis."""

    def analyze_impact(self, change: Any) -> Any:
        ...
