"""Unit tests for CitationBuilderService (Phase 8)."""

from __future__ import annotations


from ria.application.citation_builder import CitationBuilderService
from ria.domain.models.context_evidence import ContextEvidence


def test_citation_builder_service() -> None:
    svc = CitationBuilderService()
    ev = ContextEvidence(
        id="main",
        kind="function",
        content="def main(): pass",
        location_path="main.py",
        line_range=(1, 5),
    )

    citations = svc.build_citations((ev,))
    assert len(citations) == 1
    assert citations[0].file_path == "main.py"
    assert citations[0].line_start == 1
    assert citations[0].line_end == 5
