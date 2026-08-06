"""Unit tests for CitationAttachmentService (Phase 7)."""

from __future__ import annotations


from ria.application.citation_attachment import CitationAttachmentService
from ria.domain.models.prompt_context import ContextCitation


def test_citation_attachment_service() -> None:
    svc = CitationAttachmentService()
    ctx_cit = ContextCitation(
        repository="repo1",
        file_path="main.py",
        symbol_name="main",
        line_start=1,
        line_end=10,
    )

    res = svc.attach_citations("Explanation answer", (ctx_cit,))
    assert len(res) == 1
    assert res[0].file_path == "main.py"
    assert res[0].symbol_name == "main"
