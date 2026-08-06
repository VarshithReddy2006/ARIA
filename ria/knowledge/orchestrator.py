"""Knowledge Orchestrator implementing KnowledgeOrchestratorPort."""

import time

from ria.domain.common.value_objects import UUIDv4
from ria.domain.context.entities import ContextPackage
from ria.domain.knowledge.entities import KnowledgeResponse
from ria.domain.knowledge.value_objects import (
    ConversationTurn,
    KnowledgeRequest,
    KnowledgeStatistics,
    ReasoningPolicy,
)
from ria.knowledge.provider_registry import ProviderRegistry
from ria.knowledge.response_formatter import ResponseFormatter
from ria.ports.knowledge.conversation import ConversationManagerPort
from ria.ports.knowledge.intent import IntentAnalyzerPort
from ria.ports.knowledge.orchestrator import KnowledgeOrchestratorPort
from ria.ports.knowledge.prompt import PromptBuilderPort
from ria.ports.knowledge.validator import ResponseValidatorPort


class KnowledgeOrchestrator(KnowledgeOrchestratorPort):
    """Orchestrator coordinating Intent Analyzer, Prompt Builder, Provider Registry, Validator, and Formatter."""

    def __init__(
        self,
        intent_analyzer: IntentAnalyzerPort,
        prompt_builder: PromptBuilderPort,
        provider_registry: ProviderRegistry,
        validator: ResponseValidatorPort,
        formatter: ResponseFormatter,
        conversation_manager: ConversationManagerPort,
    ) -> None:
        self._intent_analyzer = intent_analyzer
        self._prompt_builder = prompt_builder
        self._registry = provider_registry
        self._validator = validator
        self._formatter = formatter
        self._conv_mgr = conversation_manager

    def process_request(
        self,
        request: KnowledgeRequest,
        context: ContextPackage,
    ) -> KnowledgeResponse:
        req_id = UUIDv4.generate().value

        # 1. Analyze Intent
        t0 = time.perf_counter()
        intent = self._intent_analyzer.analyze_intent(request.question, context)
        intent_ms = (time.perf_counter() - t0) * 1000.0

        # 2. Build Prompt
        t0 = time.perf_counter()
        prompt = self._prompt_builder.build_prompt(request.question, context, intent)
        prompt_ms = (time.perf_counter() - t0) * 1000.0

        # 3. Get Provider & Invoke
        t0 = time.perf_counter()
        provider = self._registry.get_provider(request.provider_config.provider_name)
        raw_response = provider.generate_response(prompt, request.provider_config, ReasoningPolicy())
        prov_ms = (time.perf_counter() - t0) * 1000.0

        # 4. Validate Response
        t0 = time.perf_counter()
        grounded_answer = self._validator.validate_response(raw_response, context)
        val_ms = (time.perf_counter() - t0) * 1000.0

        # 5. Format Content
        t0 = time.perf_counter()
        formatted_str = self._formatter.format_markdown(grounded_answer)
        fmt_ms = (time.perf_counter() - t0) * 1000.0

        # 6. Add turn to conversation history
        turn = ConversationTurn(user_message=request.question, assistant_response=grounded_answer.answer_text)
        self._conv_mgr.add_turn(request.conversation_id, turn)

        stats = KnowledgeStatistics(
            intent_ms=intent_ms,
            prompt_ms=prompt_ms,
            provider_ms=prov_ms,
            validation_ms=val_ms,
            format_ms=fmt_ms,
        )

        return KnowledgeResponse(
            request_id=req_id,
            answer=grounded_answer,
            formatted_content=formatted_str,
            statistics=stats,
            is_success=True,
        )
