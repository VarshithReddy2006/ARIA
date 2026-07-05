"""Base interface for all Modular Inspection Packs."""

from abc import ABC, abstractmethod
from typing import List

from models.inspection import Finding, InspectionContext


class InspectionPack(ABC):
    """Abstract base class for all inspection packs."""

    @abstractmethod
    def inspect(self, context: InspectionContext) -> List[Finding]:
        """Analyzes the repository context and compiles a list of findings."""
        pass
