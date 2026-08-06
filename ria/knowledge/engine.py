"""Knowledge Engine entry point."""

from ria.domain.context.entities import ContextPackage
from ria.domain.knowledge.entities import KnowledgeResponse
from ria.domain.knowledge.value_objects import KnowledgeRequest
from ria.ports.knowledge.orchestrator import KnowledgeOrchestratorPort


class KnowledgeEngine:
    """Core KnowledgeEngine entry point."""

    def __init__(self, orchestrator: KnowledgeOrchestratorPort) -> None:
        self._orchestrator = orchestrator

    def answer_question(
        self,
        request: KnowledgeRequest,
        context: ContextPackage,
    ) -> KnowledgeResponse:
        return self._orchestrator.process_request(request, context)
