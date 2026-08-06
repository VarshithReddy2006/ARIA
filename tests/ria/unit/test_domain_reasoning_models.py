"""Unit tests for Milestone 9 Phase 1 AI Reasoning Domain Models."""

from __future__ import annotations

import pytest

from ria.domain.models.prompt_context import PromptContext
from ria.domain.models.reasoning_id import ReasoningId
from ria.domain.models.reasoning_model import (
    ModelRequest,
    ModelResponse,
    PromptExecution,
    PromptTemplate,
    ProviderConfiguration,
    StreamingChunk,
    StreamingSession,
)
from ria.domain.models.reasoning_pipeline import ReasoningPlan, ReasoningStep
from ria.domain.models.reasoning_request import ReasoningContext, ReasoningRequest
from ria.domain.models.reasoning_result import (
    ReasoningCacheKey,
    ReasoningCitation,
    ReasoningEvidence,
    ReasoningFingerprint,
    ReasoningMetadata,
    ReasoningResult,
    ReasoningStatistics,
    ResponseQuality,
    ValidationResult,
)


def test_reasoning_id_invariants() -> None:
    rid1 = ReasoningId.for_reasoning("mock", "digest1")
    rid2 = ReasoningId.for_reasoning("mock", "digest1")

    assert rid1 == rid2
    assert str(rid1) == rid1.value

    with pytest.raises(ValueError, match="non-empty string"):
        ReasoningId("")


def test_provider_configuration_and_model_request() -> None:
    config = ProviderConfiguration(
        provider_name="openai", model_name="gpt-4o", temperature=0.5
    )
    req = ModelRequest(prompt_text="Explain main", system_prompt="System prompt")
    resp = ModelResponse(raw_text="Explanation", model_name="gpt-4o")

    assert config.provider_name == "openai"
    assert req.prompt_text == "Explain main"
    assert resp.raw_text == "Explanation"

    with pytest.raises(ValueError, match="temperature must be within"):
        ProviderConfiguration(
            provider_name="openai", model_name="gpt-4o", temperature=3.0
        )


def test_prompt_template_and_execution() -> None:
    tmpl = PromptTemplate(name="t1", template_text="Hello {name}")
    exec_rec = PromptExecution(template_name="t1", rendered_prompt="Hello World")

    assert tmpl.name == "t1"
    assert exec_rec.rendered_prompt == "Hello World"


def test_streaming_chunk_and_session() -> None:
    session = StreamingSession(session_id="s1", model_name="mock")
    chunk = StreamingChunk(
        session_id="s1", chunk_index=0, text_delta="Hello", is_final=False
    )

    assert session.session_id == "s1"
    assert chunk.text_delta == "Hello"

    with pytest.raises(ValueError, match="chunk_index must be non-negative"):
        StreamingChunk(session_id="s1", chunk_index=-1, text_delta="err")


def test_reasoning_context_and_request() -> None:
    rid = ReasoningId.for_reasoning("mock", "d1")
    p_ctx = PromptContext()
    ctx = ReasoningContext(prompt_context=p_ctx)

    config = ProviderConfiguration("local", "mock")
    req = ReasoningRequest(
        reasoning_id=rid, prompt_context=p_ctx, provider_config=config
    )

    assert ctx.prompt_context == p_ctx
    assert req.reasoning_id == rid


def test_reasoning_pipeline_and_steps() -> None:
    step = ReasoningStep(step_index=0, thought="Analyzing evidence")
    plan = ReasoningPlan(strategy="direct", steps=(step,))

    assert plan.strategy == "direct"
    assert len(plan.steps) == 1
    assert plan.steps[0].thought == "Analyzing evidence"

    with pytest.raises(ValueError, match="step_index must be non-negative"):
        ReasoningStep(step_index=-1, thought="err")


def test_reasoning_result_and_quality() -> None:
    ev = ReasoningEvidence(
        evidence_id="e1", source_file="main.py", content_snippet="def main(): pass"
    )
    cit = ReasoningCitation(file_path="main.py", line_range=(1, 5))
    val = ValidationResult(is_valid=True, validated_claims=("claim1",))
    qual = ResponseQuality(groundedness_score=0.95, citation_accuracy=1.0)
    stats = ReasoningStatistics(
        latency_seconds=0.5, prompt_tokens=100, completion_tokens=50
    )
    meta = ReasoningMetadata(
        reasoning_id="r1", provider_name="local", model_name="mock"
    )

    fp = ReasoningFingerprint(
        prompt_digest="d1", provider_name="local", model_name="mock"
    )
    key = ReasoningCacheKey(fingerprint=fp)

    res = ReasoningResult(
        answer="Main function executes application",
        evidence=(ev,),
        citations=(cit,),
        validation=val,
        quality=qual,
        statistics=stats,
        metadata=meta,
    )

    assert res.answer == "Main function executes application"
    assert len(res.evidence) == 1
    assert res.validation.is_valid
    assert res.quality.groundedness_score == 0.95
    assert key.digest() is not None

    with pytest.raises(ValueError, match="groundedness_score must be within"):
        ResponseQuality(groundedness_score=1.5)
