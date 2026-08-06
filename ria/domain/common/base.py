"""Common base classes for RIA Domain Models."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ValueObject:
    """Base class for all immutable Value Objects in the domain model."""

    def __post_init__(self) -> None:
        """Validate invariant rules upon instantiation."""
        self._validate_invariants()

    def _validate_invariants(self) -> None:
        """Subclasses override this to enforce invariant constraints."""
        pass
