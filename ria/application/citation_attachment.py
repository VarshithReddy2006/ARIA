"""Citation Attachment application service.

Attaches structured ReasoningCitations to supported statements in the generated response.
Implements :class:`~ria.ports.reasoning.CitationAttachmentPort`.
"""

from __future__ import annotations

from typing import List, Tuple

from ria.domain.models.prompt_context import ContextCitation
from ria.domain.models.reasoning_result import ReasoningCitation
from ria.ports.reasoning import CitationAttachmentPort

__all__ = ["CitationAttachmentService"]


class CitationAttachmentService(CitationAttachmentPort):
    """Service for attaching citations to reasoning output."""

    def attach_citations(
        self,
        raw_answer: str,
        citations: Tuple[ContextCitation, ...],
    ) -> Tuple[ReasoningCitation, ...]:
        """Attach ReasoningCitations to answer."""
        attached: List[ReasoningCitation] = []

        for cit in citations:
            line_range = (
                (cit.line_start, cit.line_end)
                if cit.line_start and cit.line_end
                else None
            )

            attached.append(
                ReasoningCitation(
                    file_path=cit.file_path,
                    line_range=line_range,
                    symbol_name=cit.symbol_name,
                    repository=cit.repository,
                )
            )

        return tuple(attached)
