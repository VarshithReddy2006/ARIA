"""Response Validator Port Protocol."""

from typing import Protocol, runtime_checkable

from ria.domain.context.entities import ContextPackage
from ria.domain.knowledge.entities import GroundedAnswer, ProviderResponse


@runtime_checkable
class ResponseValidatorPort(Protocol):
    """Protocol for validating LLM responses against ContextPackage facts and citations."""

    def validate_response(
        self,
        response: ProviderResponse,
        context: ContextPackage,
    ) -> GroundedAnswer:
        """Validate response against ContextPackage facts and return GroundedAnswer with ValidationReport."""
        ...
