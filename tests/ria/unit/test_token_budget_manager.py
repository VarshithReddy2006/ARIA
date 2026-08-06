"""Unit tests for TokenBudgetManagerService (Phase 10)."""

from __future__ import annotations


from ria.application.token_budget_manager import TokenBudgetManagerService
from ria.domain.models.prompt_context import PromptContext, PromptSection
from ria.domain.models.token_budget import TokenBudget


def test_token_budget_manager_service() -> None:
    svc = TokenBudgetManagerService()

    s1 = PromptSection(title="Sec1", content="hello world", token_count=100)
    s2 = PromptSection(title="Sec2", content="long text section", token_count=200)

    p_ctx = PromptContext(sections=(s1, s2), total_tokens=300)
    budget = TokenBudget(max_tokens=150)

    res = svc.enforce_budget((p_ctx,), budget)

    assert res.total_tokens <= 150
    assert len(res.sections) == 2
