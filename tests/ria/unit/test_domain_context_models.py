"""Unit tests for Milestone 8 Phase 1 AI Context Domain Models."""

from __future__ import annotations

import pytest

from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.context_evidence import (
    ContextBundle,
    ContextCandidate,
    ContextEvidence,
)
from ria.domain.models.context_id import ContextId
from ria.domain.models.context_plan import ContextPlan
from ria.domain.models.context_request import (
    ContextRequest,
    ConversationContext,
    IntentClassification,
    RepositoryContext,
)
from ria.domain.models.context_result import (
    CompressionResult,
    ContextCacheKey,
    ContextFingerprint,
    ContextMetadata,
    ContextStatistics,
    RankingResult,
    RetrievalResult,
)
from ria.domain.models.prompt_context import (
    ContextCitation,
    PromptContext,
    PromptMessage,
    PromptSection,
)
from ria.domain.models.token_budget import TokenBudget


def test_context_id_invariants() -> None:
    cid1 = ContextId.for_context("explain", "app.py")
    cid2 = ContextId.for_context("explain", "app.py")

    assert cid1 == cid2
    assert str(cid1) == cid1.value

    with pytest.raises(ValueError, match="non-empty string"):
        ContextId("")


def test_token_budget_and_intent() -> None:
    tb = TokenBudget(max_tokens=4096)
    intent = IntentClassification(intent_type="explain_code", confidence=0.9)

    assert tb.max_tokens == 4096
    assert intent.intent_type == "explain_code"

    with pytest.raises(ValueError, match="positive"):
        TokenBudget(max_tokens=0)

    with pytest.raises(ValueError, match="confidence must be within"):
        IntentClassification(intent_type="explain_code", confidence=1.5)


def test_context_request_and_plan() -> None:
    repo_id = RepositoryId("repo1")
    sha = CommitSha("a" * 40)
    cid = ContextId.for_context("find_bug", "main")
    intent = IntentClassification(intent_type="find_bug")
    plan = ContextPlan(intent=intent, target_symbols=("main",))
    conv = ConversationContext(messages=(("user", "hi"),))
    repo_ctx = RepositoryContext(repository_name="repo1", language="python")

    req = ContextRequest(
        context_id=cid,
        query_text="find bug in main",
        repository_id=repo_id,
        commit_sha=sha,
        conversation=conv,
    )

    assert req.context_id == cid
    assert "main" in plan.target_symbols
    assert len(req.conversation.messages) == 1
    assert repo_ctx.repository_name == "repo1"


def test_context_evidence_and_bundle() -> None:
    repo_id = RepositoryId("repo1")
    sha = CommitSha("a" * 40)

    cand = ContextCandidate(
        id="c1", kind="symbol", content="def main(): pass", location_path="main.py"
    )
    ev = ContextEvidence(
        id="c1",
        kind="symbol",
        content="def main(): pass",
        location_path="main.py",
        score=0.9,
    )
    bundle = ContextBundle(repository_id=repo_id, commit_sha=sha, evidence_items=(ev,))

    assert cand.id == "c1"
    assert len(bundle.evidence_items) == 1
    assert bundle.evidence_items[0].score == 0.9

    with pytest.raises(ValueError, match="score must be within"):
        ContextEvidence(
            id="c1", kind="symbol", content="pass", location_path="a.py", score=-0.1
        )


def test_prompt_context_and_citations() -> None:
    sec = PromptSection(title="Evidence", content="def foo(): pass", token_count=10)
    msg = PromptMessage(role="user", content="Explain foo")
    cit = ContextCitation(repository="repo1", file_path="foo.py", symbol_name="foo")

    p_ctx = PromptContext(
        sections=(sec,), messages=(msg,), citations=(cit,), total_tokens=10
    )

    assert len(p_ctx.sections) == 1
    assert len(p_ctx.messages) == 1
    assert len(p_ctx.citations) == 1
    assert p_ctx.citations[0].symbol_name == "foo"


def test_context_results_and_identity() -> None:
    repo_id = RepositoryId("repo1")
    sha = CommitSha("a" * 40)
    fp = ContextFingerprint(query_text="explain code", intent_type="explain_code")
    key = ContextCacheKey(repository_id=repo_id, commit_sha=sha, fingerprint=fp)

    ret = RetrievalResult()
    rank = RankingResult()
    comp = CompressionResult()
    meta = ContextMetadata(
        context_id="ctx1", repository_id="repo1", commit_sha=sha.value
    )
    stats = ContextStatistics(candidates_retrieved=5, evidence_selected=2)

    assert key.digest() is not None
    assert ret.retrieval_time_seconds == 0.0
    assert rank.ranking_time_seconds == 0.0
    assert comp.compression_ratio == 1.0
    assert stats.evidence_selected == 2
    assert meta.context_id == "ctx1"
