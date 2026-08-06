"""Citation Builder Port Definition."""

from typing import Protocol, Any


class CitationBuilderPort(Protocol):
    """Port interface for building citations."""

    def build_citations(self, context: Any) -> Any:
        ...
