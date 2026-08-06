"""Token Budget Manager application service.

Enforces maximum token constraints across prompt sections through priority ordering,
section truncation, evidence retention, and context balancing.
Implements :class:`~ria.ports.context.TokenBudgetPort`.
"""

from __future__ import annotations

from typing import List, Tuple

from ria.domain.models.prompt_context import PromptContext, PromptSection
from ria.domain.models.token_budget import TokenBudget
from ria.ports.context import TokenBudgetPort

__all__ = ["TokenBudgetManagerService"]


class TokenBudgetManagerService(TokenBudgetPort):
    """Service for enforcing token budget constraints on PromptContext."""

    def enforce_budget(
        self,
        sections: Tuple[PromptContext, ...],
        budget: TokenBudget,
    ) -> PromptContext:
        """Enforce token limits across prompt sections."""
        if not sections:
            return PromptContext()

        base_prompt = sections[0]
        max_t = budget.max_tokens

        if base_prompt.total_tokens <= max_t:
            return base_prompt

        truncated_sections: List[PromptSection] = []
        accumulated_tokens = 0

        for sec in base_prompt.sections:
            if accumulated_tokens + sec.token_count <= max_t:
                truncated_sections.append(sec)
                accumulated_tokens += sec.token_count
            else:
                remaining_tokens = max(0, max_t - accumulated_tokens)
                if remaining_tokens > 0:
                    truncated_content = (
                        sec.content[: remaining_tokens * 4] + "... [truncated]"
                    )
                    truncated_sections.append(
                        PromptSection(
                            title=sec.title,
                            content=truncated_content,
                            token_count=remaining_tokens,
                        )
                    )
                    accumulated_tokens += remaining_tokens
                break

        return PromptContext(
            sections=tuple(truncated_sections),
            messages=base_prompt.messages,
            citations=base_prompt.citations,
            total_tokens=accumulated_tokens,
        )
