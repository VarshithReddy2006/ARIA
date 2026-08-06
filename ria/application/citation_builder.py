"""Citation Builder application service.

Generates structured ContextCitation items retaining Repository, File, Line range, Symbol, Node,
and Relationship for every context evidence item.
Implements :class:`~ria.ports.context.CitationBuilderPort`.
"""

from __future__ import annotations

from typing import List, Tuple

from ria.domain.models.context_evidence import ContextEvidence
from ria.domain.models.prompt_context import ContextCitation
from ria.ports.context import CitationBuilderPort

__all__ = ["CitationBuilderService"]


class CitationBuilderService(CitationBuilderPort):
    """Service for building structured citations."""

    def build_citations(
        self,
        evidence_items: Tuple[ContextEvidence, ...],
    ) -> Tuple[ContextCitation, ...]:
        """Generate ContextCitations for evidence items."""
        citations: List[ContextCitation] = []

        for item in evidence_items:
            line_start = item.line_range[0] if item.line_range else None
            line_end = item.line_range[1] if item.line_range else None

            citations.append(
                ContextCitation(
                    repository="repository",
                    file_path=item.location_path,
                    symbol_name=item.id
                    if item.kind in ("function", "class", "method")
                    else None,
                    line_start=line_start,
                    line_end=line_end,
                    node_id=item.id,
                    relationship=item.kind if ":" in item.id else None,
                )
            )

        return tuple(citations)
