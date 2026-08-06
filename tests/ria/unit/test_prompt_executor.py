"""Unit tests for PromptExecutorService (Phase 4)."""

from __future__ import annotations


from ria.application.prompt_executor import PromptExecutorService
from ria.domain.models.prompt_context import PromptContext, PromptSection
from ria.domain.models.reasoning_model import PromptTemplate


def test_prompt_executor_service() -> None:
    svc = PromptExecutorService()
    sec = PromptSection(title="Evidence", content="def main(): pass")
    p_ctx = PromptContext(sections=(sec,))

    tmpl = PromptTemplate(name="default", template_text="Context:\n{context}")
    exec_rec = svc.execute_prompt(p_ctx, tmpl)

    assert exec_rec.template_name == "default"
    assert "Evidence" in exec_rec.rendered_prompt
    assert "def main(): pass" in exec_rec.rendered_prompt

    model_req = svc.create_model_request(p_ctx)
    assert "def main(): pass" in model_req.prompt_text
