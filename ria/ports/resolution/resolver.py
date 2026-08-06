"""Resolution Engine Port Protocol."""

from typing import Protocol, runtime_checkable

from ria.domain.index.units import IndexBatch
from ria.domain.resolution.entities import ResolvedFactSet


@runtime_checkable
class ResolutionEnginePort(Protocol):
    """Protocol for high-level Semantic Resolution Engine orchestrating multi-language symbol resolution.

    Preconditions: IndexBatch must contain immutable ParseUnits.
    Postconditions: Returns immutable ResolvedFactSet containing all extracted symbols, definitions, and relations.
    """

    def resolve_batch(self, batch: IndexBatch) -> ResolvedFactSet:
        """Resolve all symbols, definitions, references, calls, imports, and inheritance across an IndexBatch."""
        ...
