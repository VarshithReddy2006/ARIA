"""Reasoning Pipeline application service.

Orchestrates deterministic AI reasoning pipeline: PromptContext -> ModelRequest -> Model -> Response -> Structured ReasoningResult.
"""

from __future__ import annotations

import time
from typing import Optional

from ria.application.prompt_executor import PromptExecutorService
from ria.domain.models.prompt_context import PromptContext
from ria.domain.models.reasoning_model import ProviderConfiguration
from ria.domain.models.reasoning_result import (
    ReasoningMetadata,
    ReasoningResult,
    ReasoningStatistics,
)
from ria.ports.reasoning import ModelProviderPort

__all__ = ["ReasoningPipelineService"]


class ReasoningPipelineService:
    """Service orchestrating deterministic reasoning execution."""

    def __init__(self, prompt_executor: Optional[PromptExecutorService] = None) -> None:
        self._prompt_executor = prompt_executor or PromptExecutorService()

    def run_pipeline(
        self,
        prompt_context: PromptContext,
        provider: ModelProviderPort,
        config: ProviderConfiguration,
    ) -> ReasoningResult:
        """Run reasoning pipeline over PromptContext."""
        t0 = time.perf_counter()

        # 1. Format ModelRequest
        req = self._prompt_executor.create_model_request(prompt_context)

        # 2. Execute Model
        resp = provider.execute_model(req, config)

        elapsed = time.perf_counter() - t0

        stats = ReasoningStatistics(
            latency_seconds=elapsed,
            prompt_tokens=prompt_context.total_tokens,
            completion_tokens=resp.token_count,
        )

        meta = ReasoningMetadata(
            reasoning_id="rsn_pipe",
            provider_name=provider.provider_name(),
            model_name=resp.model_name,
        )

        return ReasoningResult(
            answer=resp.raw_text,
            statistics=stats,
            metadata=meta,
        )
