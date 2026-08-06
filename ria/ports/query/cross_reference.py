"""Cross Reference Port Definition."""

from typing import Protocol, Any


class CrossReferencePort(Protocol):
    """Port interface for cross references."""

    def find_references(self, target: Any) -> Any: ...
