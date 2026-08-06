"""Verification Engine Port Protocol."""

from typing import Protocol, runtime_checkable

from ria.domain.agent.entities import ExecutionContext
from ria.domain.agent.value_objects import VerificationResult


@runtime_checkable
class VerificationEnginePort(Protocol):
    """Protocol for verifying goal execution completeness and accuracy."""

    def verify(
        self,
        context: ExecutionContext,
    ) -> VerificationResult:
        """Verify execution context and return VerificationResult."""
        ...
