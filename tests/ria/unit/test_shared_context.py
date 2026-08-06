"""Unit tests for SharedContextManagerService (Phase 7)."""

from __future__ import annotations


from ria.application.shared_context_manager import SharedContextManagerService
from ria.domain.models.prompt_context import PromptContext, PromptSection


def test_shared_context_manager_service() -> None:
    svc = SharedContextManagerService()
    c1 = svc.get_context()
    assert c1.version == 1

    p2 = PromptContext(sections=(PromptSection(title="Section", content="content"),))
    c2 = svc.update_context(p2)

    assert c2.version == 2
    assert len(c2.prompt_context.sections) == 1
