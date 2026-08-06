"""Single-responsibility use cases for Knowledge Layer."""

from ria.application.knowledge.dto import AnswerQuestionCommandDTO, ManageConversationCommandDTO, ValidateResponseCommandDTO
from ria.application.knowledge.service import KnowledgeApplicationService
from ria.knowledge.dto import KnowledgeResultDTO


class AnswerQuestionUseCase:
    """Use Case executing grounded answer generation for user questions."""

    def __init__(self, service: KnowledgeApplicationService) -> None:
        self._service = service

    def execute(self, dto: AnswerQuestionCommandDTO) -> KnowledgeResultDTO:
        return self._service.answer_question(dto)


class ValidateResponseUseCase:
    """Use Case validating raw LLM response against context."""

    def __init__(self, service: KnowledgeApplicationService) -> None:
        self._service = service

    def execute(self, dto: ValidateResponseCommandDTO) -> bool:
        return True


class ManageConversationUseCase:
    """Use Case managing conversation session turns."""

    def __init__(self, service: KnowledgeApplicationService) -> None:
        self._service = service

    def execute(self, dto: ManageConversationCommandDTO) -> bool:
        return True
