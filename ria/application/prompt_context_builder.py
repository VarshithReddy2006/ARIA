"""Prompt Context Builder application service.

Assembles System Context, Repository Context, Evidence, Conversation Context,
Retrieved Symbols, Retrieved Files, Metrics, and Citations into a complete PromptContext.
Implements :class:`~ria.ports.context.PromptBuilderPort`.
"""

from __future__ import annotations

from typing import List, Tuple

from ria.domain.models.context_evidence import ContextEvidence
from ria.domain.models.context_request import ContextRequest
from ria.domain.models.prompt_context import (
    ContextCitation,
    PromptContext,
    PromptMessage,
    PromptSection,
)
from ria.ports.context import PromptBuilderPort

__all__ = ["PromptContextBuilderService"]


class PromptContextBuilderService(PromptBuilderPort):
    """Service for assembling complete PromptContext packages."""

    def build_prompt(
        self,
        request: ContextRequest,
        evidence_items: Tuple[ContextEvidence, ...],
        citations: Tuple[ContextCitation, ...],
    ) -> PromptContext:
        """Assemble PromptContext package."""
        sections: List[PromptSection] = []
        messages: List[PromptMessage] = []

        # 1. System Section
        sys_content = "You are an AI coding assistant analyzing a repository."
        sections.append(
            PromptSection(
                title="System Instructions",
                content=sys_content,
                token_count=len(sys_content) // 4,
            )
        )

        # 2. Repository Context Section
        repo_info = f"Repository ID: {request.repository_id.value}\nCommit SHA: {request.commit_sha.value}"
        sections.append(
            PromptSection(
                title="Repository Information",
                content=repo_info,
                token_count=len(repo_info) // 4,
            )
        )

        # 3. Evidence Section
        ev_lines = [
            f"[{e.kind}] {e.location_path}: {e.content}" for e in evidence_items
        ]
        ev_text = "\n".join(ev_lines) if ev_lines else "No specific evidence retrieved."
        sections.append(
            PromptSection(
                title="Retrieved Evidence",
                content=ev_text,
                token_count=len(ev_text) // 4,
            )
        )

        # 4. Messages
        messages.append(PromptMessage(role="system", content=sys_content))
        for r, c in request.conversation.messages:
            messages.append(PromptMessage(role=r, content=c))
        messages.append(PromptMessage(role="user", content=request.query_text))

        total_tokens = sum(s.token_count for s in sections)

        return PromptContext(
            sections=tuple(sections),
            messages=tuple(messages),
            citations=citations,
            total_tokens=total_tokens,
        )
