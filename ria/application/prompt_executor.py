"""Prompt Executor application service.

Renders and formats PromptContext using PromptTemplate to produce ModelRequest and PromptExecution records.
Implements :class:`~ria.ports.reasoning.PromptExecutorPort`.
"""

from __future__ import annotations

import time

from ria.domain.models.prompt_context import PromptContext
from ria.domain.models.reasoning_model import (
    ModelRequest,
    PromptExecution,
    PromptTemplate,
)
from ria.ports.reasoning import PromptExecutorPort

__all__ = ["PromptExecutorService"]


class PromptExecutorService(PromptExecutorPort):
    """Service for rendering prompt templates and formatting ModelRequests."""

    def execute_prompt(
        self,
        prompt_context: PromptContext,
        template: PromptTemplate,
    ) -> PromptExecution:
        """Render PromptContext into a PromptExecution record."""
        t0 = time.perf_counter()

        section_texts = [
            f"=== {s.title} ===\n{s.content}" for s in prompt_context.sections
        ]
        body = "\n\n".join(section_texts)

        rendered = template.template_text.replace("{context}", body)
        elapsed = time.perf_counter() - t0

        return PromptExecution(
            template_name=template.name,
            rendered_prompt=rendered,
            execution_time_seconds=elapsed,
        )

    def create_model_request(
        self,
        prompt_context: PromptContext,
        system_instructions: str = "Analyze repository evidence and provide a grounded explanation.",
    ) -> ModelRequest:
        """Construct ModelRequest from PromptContext."""
        section_texts = [
            f"=== {s.title} ===\n{s.content}" for s in prompt_context.sections
        ]
        full_text = "\n\n".join(section_texts)

        return ModelRequest(
            prompt_text=full_text,
            system_prompt=system_instructions,
        )
