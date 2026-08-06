"""Architecture Analysis Port Definition."""

from typing import Protocol, Any


class ArchitectureAnalysisPort(Protocol):
    """Port interface for architecture analysis."""

    def analyze(self, repo_id: Any) -> Any:
        ...
