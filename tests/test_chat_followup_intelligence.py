"""Comprehensive test suite for ARIA Chat Intelligence & Dynamic Follow-Up Engine.

Tests covered:
1. Entity-aware follow-up synthesis (files, symbols, endpoints, artifacts).
2. Rejection of generic template questions.
3. Multi-stage ranking and filtering.
4. Non-duplication of current question or conversation history.
5. Conversational progression across multiple turns.
6. Unresolved engineering threads extraction.
7. Intent-aware dynamic answer schemas in ContextBuilder.
8. Anti-hallucination instruction invariants for all LLM providers.
9. RetrievalPipeline output contains synthesized follow_ups.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from services.chat.followup_engine import FollowUpEngine
from services.chat.context_builder import ContextBuilder
from services.chat.retrieval_pipeline import RetrievalPipeline
from services.llm.base_provider import BaseLLMProvider, ProviderHealth
from services.chat.provider_manager import ProviderManager, ProviderEntry


class _MockTestProvider(BaseLLMProvider):
    def __init__(self, name="mock-provider"):
        self.name = name
        self.model = "test-model"

    async def health_check(self):
        return ProviderHealth(
            healthy=True,
            provider=self.name,
            model=self.model,
            authenticated=True,
            latency_ms=10.0,
        )

    async def generate(self, prompt, **kwargs):
        return (
            "### Answer\n`WebUI/app.js` sends the URL to `/predict` in `Backend/app.py`.\n\n"
            "### Request Flow\n`Backend/app.py` passes the URL to `generate_df_from_url()` in `Backend/features.py`,\n"
            "which creates features for `predict_model()` in `Backend/utils.py`.\n\n"
            "### Key Components\n- `Backend/app.py`\n- `Backend/features.py`\n- `Backend/utils.py`\n- `random_forest_model.pkl`\n\n"
            "### Evidence\n**File:** `Backend/app.py`, **Lines:** 1–40, **Role:** API entry point.\n\n"
            "### Failure / Risk Points\nMalformatted URLs or missing pickled model file."
        )

    async def stream(self, prompt, **kwargs):
        text = await self.generate(prompt, **kwargs)
        for token in text.split(" "):
            yield token + " "


# ── Tests ───────────────────────────────────────────────────────────────────


def test_followup_engine_generates_concrete_entities():
    """1. Follow-up questions contain concrete files, symbols, and endpoints from the answer."""
    engine = FollowUpEngine()

    question = "How does the machine learning inference pipeline work?"
    answer = (
        "`WebUI/app.js` submits URLs to `/predict` in `Backend/app.py`. "
        "The route passes the payload to `generate_df_from_url()` in `Backend/features.py`, "
        "which transforms the string into numeric features for `predict_model()` in `Backend/utils.py`. "
        "The model is loaded from `random_forest_model.pkl`."
    )
    chunks = [
        {
            "metadata": {
                "file_path": "Backend/features.py",
                "matched_symbols": "generate_df_from_url",
            },
            "content": "def generate_df_from_url(url): ...",
        },
        {
            "metadata": {
                "file_path": "Backend/utils.py",
                "matched_symbols": "predict_model",
            },
            "content": "def predict_model(features): ...",
        },
    ]

    follow_ups = engine.synthesize_follow_ups(
        repo_name="VarshithReddy2006/PhishingWebsite_Detection",
        question=question,
        answer=answer,
        intent="API_FLOW",
        code_chunks=chunks,
        source_files=["Backend/app.py", "Backend/features.py", "Backend/utils.py"],
    )

    assert len(follow_ups) in (2, 3)
    combined = " ".join(follow_ups)

    # Invariant: Contains concrete repository entities
    assert any(
        ent in combined
        for ent in ("Backend/features.py", "Backend/utils.py", "Backend/app.py")
    )
    assert any(
        sym in combined
        for sym in (
            "generate_df_from_url",
            "predict_model",
            "/predict",
            "random_forest_model.pkl",
        )
    )

    # Invariant: Does not contain generic questions
    assert "What are the core dependencies?" not in combined
    assert "What are the main entry points?" not in combined


def test_followup_engine_rejects_duplicates_and_prior_turns():
    """2. Engine rejects questions already asked in previous turns or restating the current question."""
    engine = FollowUpEngine()

    question = "How does Backend/app.py work?"
    answer = "`Backend/app.py` initializes Flask and routes requests."
    history = [
        {
            "role": "user",
            "content": "How does `generate_df_from_url()` in `Backend/features.py` execute its core logic?",
        },
        {"role": "assistant", "content": "It parses URLs into 16 features."},
    ]

    follow_ups = engine.synthesize_follow_ups(
        repo_name="test/repo",
        question=question,
        answer=answer,
        intent="FILE_EXPLANATION",
        source_files=["Backend/app.py", "Backend/features.py"],
        conversation_history=history,
    )

    for q in follow_ups:
        # Invariant: does not duplicate prior question
        assert "How does Backend/app.py work?" not in q
        assert "It parses URLs into 16 features" not in q


def test_followup_engine_extracts_unresolved_threads():
    """3. Unresolved engineering threads generate targeted follow-up candidates."""
    engine = FollowUpEngine()

    question = "How does model prediction execute?"
    answer = "`predict_model()` loads `random_forest_model.pkl` to compute inference."
    chunks = [
        {
            "metadata": {
                "file_path": "Backend/utils.py",
                "matched_symbols": "predict_model",
            }
        }
    ]

    follow_ups = engine.synthesize_follow_ups(
        repo_name="test/repo",
        question=question,
        answer=answer,
        intent="API_FLOW",
        code_chunks=chunks,
        source_files=["Backend/utils.py", "random_forest_model.pkl"],
    )

    combined = " ".join(follow_ups)
    assert "random_forest_model.pkl" in combined or "Backend/utils.py" in combined


def test_context_builder_generates_intent_tailored_schemas():
    """4. ContextBuilder produces intent-specific Response Formats."""
    builder = ContextBuilder()

    # API_FLOW
    ctx_api = builder.build(
        repo_name="owner/repo",
        question="How does /predict work?",
        intent_name="API_FLOW",
    )
    assert "### Request Flow" in ctx_api.prompt
    assert "### Relevant Files" in ctx_api.prompt
    assert "### Failure Points" in ctx_api.prompt

    # ARCHITECTURE
    ctx_arch = builder.build(
        repo_name="owner/repo",
        question="Explain architecture",
        intent_name="ARCHITECTURE",
    )
    assert "### Architecture Model" in ctx_arch.prompt
    assert "### Dependency Flow" in ctx_arch.prompt
    assert "### Architectural Strengths" in ctx_arch.prompt

    # FILE_EXPLANATION
    ctx_file = builder.build(
        repo_name="owner/repo",
        question="Explain app.py",
        intent_name="FILE_EXPLANATION",
    )
    assert "### File Role" in ctx_file.prompt
    assert "### Responsibilities" in ctx_file.prompt
    assert "### Dependencies" in ctx_file.prompt

    # CHANGE_PLANNING
    ctx_plan = builder.build(
        repo_name="owner/repo",
        question="How to add auth?",
        intent_name="CHANGE_PLANNING",
    )
    assert "### Proposed Change" in ctx_plan.prompt
    assert "### Directly Affected Files" in ctx_plan.prompt
    assert "### Blast Radius" in ctx_plan.prompt


def test_context_builder_enforces_anti_hallucination_rules():
    """5. System instructions strictly forbid hallucination and require explicit unknown labeling."""
    builder = ContextBuilder()
    ctx = builder.build(
        repo_name="my/repo", question="Explain pipeline", intent_name="API_FLOW"
    )

    sys_inst = ctx.system_instruction
    assert "Do NOT invent files, functions, endpoints" in sys_inst
    assert "state that it is unknown or inferred" in sys_inst
    assert "Always prefer concrete facts: concrete file -> concrete symbol" in sys_inst


@pytest.mark.asyncio
async def test_retrieval_pipeline_emits_dynamic_follow_ups():
    """6. RetrievalPipeline retrieve and retrieve_stream output dynamic follow-ups."""
    mock_emb = MagicMock()
    mock_chroma = MagicMock()
    mock_provider = _MockTestProvider()
    e1 = ProviderEntry(name="gemini", provider=mock_provider, priority=1)
    pm = ProviderManager(providers=[e1])

    pipeline = RetrievalPipeline(
        embedding_service=mock_emb,
        chroma_store=mock_chroma,
        provider_manager=pm,
    )

    # Non-streaming
    res = await pipeline.retrieve(
        repo_name="owner/repo", question="How does the inference pipeline work?"
    )
    assert "follow_ups" in res
    assert isinstance(res["follow_ups"], list)
    assert len(res["follow_ups"]) in (2, 3)

    # Streaming
    sse_events = []
    async for sse in pipeline.retrieve_stream(
        repo_name="owner/repo", question="How does /predict work?"
    ):
        sse_events.append(sse)

    done_event = [e for e in sse_events if '"status": "done"' in e]
    assert len(done_event) == 1
    assert '"follow_ups":' in done_event[0]


def test_multi_turn_conversational_depth_progression():
    """7. Follow-ups progress deeper across conversation turns without repeating."""
    engine = FollowUpEngine()

    # Turn 1: High level pipeline question
    turn1_q = "How does the machine learning inference pipeline work?"
    turn1_a = "WebUI submits to `/predict` in `Backend/app.py`, which calls `generate_df_from_url()` in `Backend/features.py`."
    turn1_followups = engine.synthesize_follow_ups(
        repo_name="owner/repo",
        question=turn1_q,
        answer=turn1_a,
        intent="API_FLOW",
        source_files=["Backend/app.py", "Backend/features.py"],
    )

    assert len(turn1_followups) >= 2
    turn2_q = turn1_followups[0]  # user chooses first follow-up

    # Turn 2: Function drilldown
    turn2_a = "`generate_df_from_url()` parses the URL structure, extracts 16 features, and passes a DataFrame to `predict_model()` in `Backend/utils.py`."
    turn2_followups = engine.synthesize_follow_ups(
        repo_name="owner/repo",
        question=turn2_q,
        answer=turn2_a,
        intent="FILE_EXPLANATION",
        source_files=["Backend/features.py", "Backend/utils.py"],
        conversation_history=[
            {"role": "user", "content": turn1_q},
            {"role": "assistant", "content": turn1_a},
            {"role": "user", "content": turn2_q},
        ],
    )

    assert len(turn2_followups) >= 2
    # Invariant: Turn 2 follow-ups do not duplicate turn 1 question or turn 2 question
    for q in turn2_followups:
        assert q != turn1_q
        assert q != turn2_q


def test_dependency_and_architecture_intent_followups():
    """8. Dependency analysis produces coupling and cycle-breaking follow-ups."""
    engine = FollowUpEngine()

    q = "What dependencies exist around Backend/utils.py?"
    a = "`Backend/utils.py` is imported by `Backend/app.py`, `Backend/train.py`, and `Backend/retrain.py`. It has high centrality."
    follow_ups = engine.synthesize_follow_ups(
        repo_name="owner/repo",
        question=q,
        answer=a,
        intent="DEPENDENCY",
        source_files=["Backend/utils.py", "Backend/app.py", "Backend/train.py"],
    )

    combined = " ".join(follow_ups)
    assert any(
        f in combined
        for f in ("Backend/utils.py", "Backend/app.py", "Backend/train.py")
    )


def test_full_8_turn_progressive_depth():
    """9. Complete 8-turn progressive conversation test from Overview down to Tests."""
    engine = FollowUpEngine()
    repo = "VarshithReddy2006/PhishingWebsite_Detection"

    conversation_history = []

    turns = [
        (
            "What does this repository do?",
            "This repository implements a phishing website detector using Flask (`Backend/app.py`) and a Random Forest model (`Backend/utils.py`).",
            "OVERVIEW",
            ["Backend/app.py", "Backend/utils.py"],
        ),
        (
            "How does the main pipeline work?",
            "The pipeline routes through `Backend/app.py` `/predict`, which invokes `generate_df_from_url()` in `Backend/features.py` and `predict_model()` in `Backend/utils.py`.",
            "API_FLOW",
            ["Backend/app.py", "Backend/features.py", "Backend/utils.py"],
        ),
        (
            "What does Backend/features.py do?",
            "`Backend/features.py` parses URLs and extracts 16 distinct domain and structural features using `generate_df_from_url()`.",
            "FILE_EXPLANATION",
            ["Backend/features.py"],
        ),
        (
            "Where is generate_df_from_url() used?",
            "`generate_df_from_url()` is called directly by `/predict` in `Backend/app.py` before passing feature vectors to `Backend/utils.py`.",
            "CALL_GRAPH",
            ["Backend/features.py", "Backend/app.py"],
        ),
        (
            "What would break if its output changed?",
            "Changing `generate_df_from_url()` feature vector schema breaks `predict_model()` in `Backend/utils.py` and the Flask response payload in `Backend/app.py`.",
            "IMPACT_ANALYSIS",
            ["Backend/features.py", "Backend/utils.py"],
        ),
        (
            "How should I safely modify it?",
            "To safely modify `generate_df_from_url()`, version the feature vector, update `predict_model()` to validate dimensions, and add fallback defaults.",
            "CHANGE_PLANNING",
            ["Backend/features.py", "Backend/utils.py"],
        ),
        (
            "What tests should I add?",
            "Add unit test fixtures in `tests/test_features.py` mocking malformed URLs and verifying DataFrame shape output of `generate_df_from_url()`.",
            "TESTING",
            ["Backend/features.py", "tests/test_features.py"],
        ),
        (
            "What should I inspect next?",
            "Inspect `Backend/train.py` and `Backend/retrain.py` to examine how `random_forest_model.pkl` is trained and versioned.",
            "READING_ORDER",
            ["Backend/train.py", "Backend/retrain.py"],
        ),
    ]

    for q, a, intent, files in turns:
        follow_ups = engine.synthesize_follow_ups(
            repo_name=repo,
            question=q,
            answer=a,
            intent=intent,
            source_files=files,
            conversation_history=conversation_history,
        )
        assert len(follow_ups) in (2, 3)
        for fu in follow_ups:
            # Must not repeat current or previous question
            assert fu != q
            for prev in conversation_history:
                assert fu != prev.get("content")

        conversation_history.append({"role": "user", "content": q})
        conversation_history.append({"role": "assistant", "content": a})


def test_question_novelty_scorer():
    """10. QuestionNoveltyScorer strictly rejects generic questions and rewards novel entities."""
    from services.chat.question_novelty import QuestionNoveltyScorer

    # Generic question rejected
    generic = QuestionNoveltyScorer.score_candidate(
        candidate_text="What are the main risks?",
        current_question="How does Backend/app.py work?",
        conversation_history=[],
        explored_entities=set(),
        unresolved_aspects=[],
    )
    assert generic.novelty_score < 0

    # Concrete entity-grounded question accepted with high score
    specific = QuestionNoveltyScorer.score_candidate(
        candidate_text="What would happen to `Backend/app.py` if `generate_df_from_url()` changed its returned feature schema?",
        current_question="How does Backend/app.py work?",
        conversation_history=[],
        explored_entities={"Backend/app.py"},
        unresolved_aspects=["feature_vector_schema"],
        current_depth=5,
    )
    assert specific.novelty_score > 70
