"""Knowledge Orchestrator Port Protocol."""

from typing import Protocol, runtime_checkable

from ria.domain.context.entities import ContextPackage
from ria.domain.knowledge.entities import KnowledgeResponse
from ria.domain.knowledge.value_objects import KnowledgeRequest


@runtime_checkable
class KnowledgeOrchestratorPort(Protocol):
    """Protocol for high-level KnowledgeOrchestrator subsystem."""

    def process_request(
        self,
        request: KnowledgeRequest,
        context: ContextPackage,
    ) -> KnowledgeResponse:
        """Process KnowledgeRequest and ContextPackage to produce KnowledgeResponse."""
        ...
