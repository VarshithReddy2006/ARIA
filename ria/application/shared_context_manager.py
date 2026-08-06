"""Shared Context Manager application service.

Manages versioned SharedContext across participating agents in an execution session.
Implements :class:`~ria.ports.agent.SharedContextPort`.
"""

from __future__ import annotations

from typing import Optional, Tuple

from ria.domain.models.agent_execution import SharedContext
from ria.domain.models.context_evidence import ContextEvidence
from ria.domain.models.prompt_context import PromptContext
from ria.ports.agent import SharedContextPort

__all__ = ["SharedContextManagerService"]


class SharedContextManagerService(SharedContextPort):
    """Service managing versioned SharedContext across agents."""

    def __init__(self, initial_context: Optional[SharedContext] = None) -> None:
        self._current_context = initial_context or SharedContext(
            prompt_context=PromptContext()
        )

    def get_context(self) -> SharedContext:
        """Retrieve active SharedContext."""
        return self._current_context

    def update_context(self, prompt_context: PromptContext) -> SharedContext:
        """Update active SharedContext with new PromptContext and increment version revision."""
        new_version = self._current_context.version + 1
        self._current_context = SharedContext(
            prompt_context=prompt_context,
            shared_evidence=self._current_context.shared_evidence,
            version=new_version,
        )
        return self._current_context

    def add_evidence(self, evidence: Tuple[ContextEvidence, ...]) -> SharedContext:
        """Add new shared evidence items and increment version revision."""
        merged_evidence = self._current_context.shared_evidence + evidence
        new_version = self._current_context.version + 1
        self._current_context = SharedContext(
            prompt_context=self._current_context.prompt_context,
            shared_evidence=merged_evidence,
            version=new_version,
        )
        return self._current_context
