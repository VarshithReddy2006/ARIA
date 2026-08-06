"""Application Service for Knowledge Layer."""

from typing import Any

from ria.application.context import BuildContextCommandDTO, ContextApplicationService
from ria.application.knowledge.dto import AnswerQuestionCommandDTO
from ria.domain.common.value_objects import UUIDv4
from ria.domain.knowledge.value_objects import (
    ConversationId,
    KnowledgeRequest,
    ProviderConfiguration,
)
from ria.knowledge.dto import KnowledgeResultDTO
from ria.knowledge.engine import KnowledgeEngine
from ria.ports.common.clock import ClockPort
from ria.ports.common.logger import LoggerPort
from ria.ports.common.metrics import MetricsPort
from ria.ports.sync.registry import RepositoryRegistryPort


class KnowledgeApplicationService:
    """Application Service coordinating Context Application Service lookup and KnowledgeEngine execution."""

    def __init__(
        self,
        knowledge_engine: KnowledgeEngine,
        context_service: ContextApplicationService,
        registry: RepositoryRegistryPort,
        clock: ClockPort,
        logger: LoggerPort,
        metrics: MetricsPort,
    ) -> None:
        self._engine = knowledge_engine
        self._context_service = context_service
        self._registry = registry
        self._clock = clock
        self._logger = logger
        self._metrics = metrics

    def answer_question(self, dto: AnswerQuestionCommandDTO) -> KnowledgeResultDTO:
        start_t = self._clock.monotonic_seconds()
        self._logger.info(
            "Executing KnowledgeApplicationService.answer_question", repo_id=dto.repo_id
        )

        st = next(
            (
                s
                for s in self._registry.list_all()
                if s.identity.repo_id.value == dto.repo_id
            ),
            None,
        )
        if st is None or st.current_commit is None:
            return KnowledgeResultDTO(
                request_id="none",
                conversation_id=dto.conversation_id or "none",
                answer_text="",
                is_grounded=False,
                grounding_score=0.0,
                total_tokens=0,
                elapsed_ms=0.0,
                is_success=False,
                error_message=f"Repository '{dto.repo_id}' is not registered or synchronized.",
            )

        try:
            # 1. Build Context Package
            ctx_dto = self._context_service.build_context(
                BuildContextCommandDTO(
                    repo_id=dto.repo_id,
                    question=dto.question,
                    max_tokens=4000,
                    format="json",
                )
            )
            if not ctx_dto.is_success:
                raise ValueError(f"Context building failed: {ctx_dto.error_message}")

            # Re-assemble package for engine
            context_pkg = self._context_service._engine._builder.build_context(
                self._context_service._engine._builder._expander._ref.__class__
                and None  # type: ignore
                or self._create_request(dto.question),
                self._context_service._search,
                self._context_service._query,
                self._context_service._fact_store,
                st.identity,
                st.current_commit,
            )

            # 2. Construct Knowledge Request
            cid_str = dto.conversation_id or UUIDv4.generate().value
            req = KnowledgeRequest(
                conversation_id=ConversationId(value=cid_str),
                question=dto.question,
                provider_config=ProviderConfiguration(provider_name=dto.provider_name),
            )

            # 3. Invoke Knowledge Engine
            response = self._engine.answer_question(req, context_pkg)

            elapsed = (self._clock.monotonic_seconds() - start_t) * 1000.0
            self._metrics.record_duration("knowledge_answer_ms", elapsed)

            return KnowledgeResultDTO(
                request_id=response.request_id,
                conversation_id=cid_str,
                answer_text=response.answer.answer_text,
                is_grounded=response.answer.validation.grounding_score.is_grounded,
                grounding_score=response.answer.validation.grounding_score.score_value,
                total_tokens=context_pkg.metadata.total_tokens,
                elapsed_ms=elapsed,
                is_success=True,
            )
        except Exception as err:
            elapsed = (self._clock.monotonic_seconds() - start_t) * 1000.0
            self._logger.error("Knowledge answer failed", exc=err, repo_id=dto.repo_id)
            return KnowledgeResultDTO(
                request_id="none",
                conversation_id=dto.conversation_id or "none",
                answer_text="",
                is_grounded=False,
                grounding_score=0.0,
                total_tokens=0,
                elapsed_ms=elapsed,
                is_success=False,
                error_message=str(err),
            )

    def _create_request(self, question: str) -> Any:
        from ria.domain.context.value_objects import (
            ContextOptions,
            ContextRequest,
            TokenBudget,
        )

        return ContextRequest(
            question=question,
            options=ContextOptions(token_budget=TokenBudget(max_tokens=4000)),
        )
