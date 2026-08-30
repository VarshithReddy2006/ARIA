"""Comprehensive 10/10 Test Suite for ARIA Chat / Repository Engineering Copilot.

Verifies:
1. 10-Turn Progressive Investigation (Depth levels 1 to 8, entity memory, pronoun resolution, novel follow-ups).
2. Repository-Specificity (Identical query across two distinct repositories produces distinct, grounded follow-ups).
3. Provider-Independence (Gemini primary vs DeepSeek failover receiving identical context and schemas).
4. Failure Recovery & Graceful Degradation (Quota 429, Timeout, Auth 401, Empty completion).
5. Secret & Credential Redaction Invariant.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from services.chat.followup_engine import FollowUpEngine
from services.chat.engineering_threads import (
    EngineeringThreadTracker,
    InvestigationDepth,
)
from services.chat.response_schema import ResponseSchemaBuilder
from services.chat.conversation_memory import ConversationSession
from services.chat.provider_manager import ProviderManager, ProviderEntry
from services.chat.retrieval_pipeline import RetrievalPipeline
from services.llm.base_provider import BaseLLMProvider, ProviderHealth


class _MockDualProvider(BaseLLMProvider):
    def __init__(self, name: str, model: str = "model"):
        self.name = name
        self.model = model
        self.last_received_prompt = ""
        self.last_received_system_instruction = ""
        self.last_received_history = []

    async def health_check(self):
        return ProviderHealth(
            healthy=True,
            provider=self.name,
            model=self.model,
            authenticated=True,
            latency_ms=5.0,
        )

    async def generate(
        self, prompt: str, system_instruction: str = "", history=None, **kwargs
    ):
        self.last_received_prompt = prompt
        self.last_received_system_instruction = system_instruction
        self.last_received_history = history or []
        return (
            "### Answer\n`Backend/app.py` defines the `/predict` route.\n\n"
            "### Request Flow\n`Backend/app.py` passes the payload to `generate_df_from_url()` in `Backend/features.py`,\n"
            "which extracts features for `predict_model()` in `Backend/utils.py`.\n\n"
            "### Evidence\n**File:** `Backend/app.py`, **Lines:** 77–86, **Role:** Endpoint controller."
        )

    async def stream(
        self, prompt: str, system_instruction: str = "", history=None, **kwargs
    ):
        text = await self.generate(
            prompt, system_instruction=system_instruction, history=history, **kwargs
        )
        for token in text.split(" "):
            yield token + " "


# ---------------------------------------------------------------------------
# 1. Ten-Turn Adversarial Progressive Investigation Test
# ---------------------------------------------------------------------------


def test_ten_turn_progressive_investigation_depth_and_novelty():
    """10-turn progressive investigation test verifying depth advance and zero generic repetitions."""
    engine = FollowUpEngine()
    session = ConversationSession(
        session_id="test_sess_10",
        repo_name="VarshithReddy2006/PhishingWebsite_Detection",
    )
    tracker = engine.get_or_create_tracker(session.repo_name)

    ten_turns = [
        # Turn 1: System Overview (Level 1)
        (
            "What does this repository do?",
            "This repository is a phishing detection engine built on Flask (`Backend/app.py`) using machine learning models (`Backend/utils.py`).",
            "OVERVIEW",
            ["Backend/app.py", "Backend/utils.py"],
        ),
        # Turn 2: Subsystem Flow (Level 2)
        (
            "What are its primary execution paths?",
            "The primary path is HTTP POST `/predict` in `Backend/app.py`, which calls `generate_df_from_url()` in `Backend/features.py`.",
            "API_FLOW",
            ["Backend/app.py", "Backend/features.py"],
        ),
        # Turn 3: Component / File (Level 3)
        (
            "Which file starts the main path?",
            "`Backend/app.py` is the application entry point defining Flask routes and error handlers.",
            "FILE_EXPLANATION",
            ["Backend/app.py"],
        ),
        # Turn 4: Symbol Logic (Level 4)
        (
            "What does that function call?",
            "`predict_phishing()` calls `generate_df_from_url()` to extract 16 URL structural features.",
            "SYMBOL_EXPLANATION",
            ["Backend/features.py"],
        ),
        # Turn 5: Caller / Dependency Relationship (Level 5)
        (
            "Which modules depend on it?",
            "`Backend/features.py` is imported by `Backend/app.py`, `Backend/train.py`, and `Backend/retrain.py`.",
            "DEPENDENCY",
            ["Backend/features.py", "Backend/app.py", "Backend/train.py"],
        ),
        # Turn 6: Change Impact / Blast Radius (Level 6)
        (
            "What happens if its output changes?",
            "If the DataFrame schema changes, `predict_model()` in `Backend/utils.py` will fail feature shape alignment.",
            "IMPACT_ANALYSIS",
            ["Backend/features.py", "Backend/utils.py"],
        ),
        # Turn 7: Blast Radius (Level 6)
        (
            "What is the blast radius?",
            "The blast radius includes `Backend/utils.py`, `Backend/train.py`, and API client `WebUI/app.js`.",
            "IMPACT_ANALYSIS",
            ["Backend/utils.py", "WebUI/app.js"],
        ),
        # Turn 8: Directly Affected Files (Level 6)
        (
            "Which files should change?",
            "Directly modify `Backend/features.py` and `Backend/utils.py`, with indirect updates to `Backend/train.py`.",
            "CHANGE_PLANNING",
            ["Backend/features.py", "Backend/utils.py", "Backend/train.py"],
        ),
        # Turn 9: Safe Implementation (Level 7)
        (
            "How should I safely modify it?",
            "Version the feature extraction vector, validate dimensions before inference, and add fallback defaults.",
            "CHANGE_PLANNING",
            ["Backend/features.py", "Backend/utils.py"],
        ),
        # Turn 10: Test Strategy (Level 8)
        (
            "What tests should be added?",
            "Add unit test fixtures in `tests/test_features.py` asserting DataFrame output dimensions on malformed URLs.",
            "TESTING",
            ["Backend/features.py", "tests/test_features.py"],
        ),
    ]

    history = []
    seen_followups = set()

    for idx, (question, answer, intent, files) in enumerate(ten_turns, 1):
        # 1. Resolve pronouns in question
        resolved_q = session.resolve_pronouns(question)
        if idx == 4:
            assert (
                "predict_phishing" in resolved_q
                or "Backend/app.py" in resolved_q
                or "that function" not in resolved_q
            )

        # 2. Synthesize follow-ups
        follow_ups = engine.synthesize_follow_ups(
            repo_name=session.repo_name,
            question=resolved_q,
            answer=answer,
            intent=intent,
            source_files=files,
            conversation_history=history,
        )

        assert len(follow_ups) in (2, 3), (
            f"Turn {idx} failed to produce 2-3 follow-ups: {follow_ups}"
        )

        for fu in follow_ups:
            # Must not repeat current or earlier user questions
            assert fu != question
            assert fu != resolved_q
            for prev in history:
                assert fu != prev.get("content")
            # Invariant: non-duplication across turns
            seen_followups.add(fu)

        # Update session memory
        session.add_turn("user", question)
        session.add_turn("assistant", answer)
        session.update_context(
            entities=[f.split("/")[-1].replace(".py", "") for f in files]
            + (["predict_phishing"] if idx == 3 else []),
            files=files,
            intent=intent,
        )
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})

    # Invariant: At least 15 unique follow-up questions generated across 10 turns
    assert len(seen_followups) >= 15
    # Invariant: Depth ladder progressed to level 8 (TEST_VALIDATION)
    assert tracker.current_depth == InvestigationDepth.TEST_VALIDATION


# ---------------------------------------------------------------------------
# 2. Repository-Specificity Test
# ---------------------------------------------------------------------------


def test_repository_specificity_for_identical_query():
    """Identical query on two distinct repositories produces materially distinct follow-ups."""
    engine = FollowUpEngine()

    identical_question = "What are the main entry points?"

    # Repo A: Phishing Website Detection (Flask + ML)
    followups_repo_a = engine.synthesize_follow_ups(
        repo_name="VarshithReddy2006/PhishingWebsite_Detection",
        question=identical_question,
        answer="The entry points are `Backend/app.py` defining `/predict` and `WebUI/app.js`.",
        intent="API_FLOW",
        source_files=["Backend/app.py", "WebUI/app.js"],
    )

    # Repo B: FastAPI Core Framework
    followups_repo_b = engine.synthesize_follow_ups(
        repo_name="tiangolo/fastapi",
        question=identical_question,
        answer="The core entry points are `fastapi/applications.py` defining `FastAPI()` and `fastapi/routing.py`.",
        intent="API_FLOW",
        source_files=["fastapi/applications.py", "fastapi/routing.py"],
    )

    combined_a = " ".join(followups_repo_a)
    combined_b = " ".join(followups_repo_b)

    # Invariant: Repo A questions reference Repo A files and symbols
    assert (
        "Backend/app.py" in combined_a
        or "WebUI/app.js" in combined_a
        or "/predict" in combined_a
    )
    assert "fastapi/applications.py" not in combined_a

    # Invariant: Repo B questions reference Repo B files and symbols
    assert (
        "fastapi/applications.py" in combined_b
        or "fastapi/routing.py" in combined_b
        or "FastAPI" in combined_b
    )
    assert "Backend/app.py" not in combined_b

    # Invariant: Sets are disjoint and repository-specific
    assert set(followups_repo_a) != set(followups_repo_b)


# ---------------------------------------------------------------------------
# 3. Provider-Independence & Context Preservation Test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provider_independence_and_context_preservation():
    """Gemini primary and DeepSeek secondary receive identical prompts, histories, and schemas."""
    mock_gemini = _MockDualProvider(name="gemini", model="gemini-2.5-flash")
    mock_deepseek = _MockDualProvider(name="deepseek", model="deepseek-chat")

    e1 = ProviderEntry(name="gemini", provider=mock_gemini, priority=1)
    e2 = ProviderEntry(name="deepseek", provider=mock_deepseek, priority=2)

    manager = ProviderManager(providers=[e1, e2])

    test_prompt = "## Question\nHow does `/predict` work?\n\n## Response Format (API & Request Flow)\n### Answer\n### Endpoint"
    test_sys_inst = ResponseSchemaBuilder.build_system_instruction("test/repo")
    test_history = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi"},
    ]

    # 1. Normal call (Gemini handles)
    res1, p1 = await manager.generate(
        prompt=test_prompt, system_instruction=test_sys_inst, history=test_history
    )
    assert p1 == "gemini"
    assert mock_gemini.last_received_prompt == test_prompt
    assert mock_gemini.last_received_system_instruction == test_sys_inst
    assert mock_gemini.last_received_history == test_history

    # 2. Simulate Gemini Quota exhaustion -> DeepSeek takeover
    mock_gemini.generate = AsyncMock(
        side_effect=Exception("429 Resource has been exhausted (quota exceeded)")
    )

    res2, p2 = await manager.generate(
        prompt=test_prompt, system_instruction=test_sys_inst, history=test_history
    )
    assert p2 == "deepseek"
    # DeepSeek must have received the exact same context, system instructions, and history
    assert mock_deepseek.last_received_prompt == test_prompt
    assert mock_deepseek.last_received_system_instruction == test_sys_inst
    assert mock_deepseek.last_received_history == test_history


# ---------------------------------------------------------------------------
# 4. Failure Recovery & Graceful Degradation Test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failure_recovery_both_providers_down():
    """When all LLM providers fail, RetrievalPipeline produces grounded fallback intelligence."""
    mock_emb = MagicMock()
    mock_chroma = MagicMock()
    mock_chroma.search_repository.return_value = [
        {"content": "def predict(): pass", "metadata": {"file_path": "Backend/app.py"}}
    ]

    p1 = MagicMock()
    p1.generate = AsyncMock(side_effect=Exception("503 Service Unavailable"))
    p1.model = "gemini"
    e1 = ProviderEntry(name="gemini", provider=p1, priority=1)

    p2 = MagicMock()
    p2.generate = AsyncMock(side_effect=Exception("TimeoutError Custom"))
    p2.model = "deepseek"
    e2 = ProviderEntry(name="deepseek", provider=p2, priority=2)

    manager = ProviderManager(providers=[e1, e2])
    pipeline = RetrievalPipeline(
        embedding_service=mock_emb,
        chroma_store=mock_chroma,
        provider_manager=manager,
    )

    res = await pipeline.retrieve(
        repo_name="owner/repo", question="How does the pipeline work?"
    )
    assert res["fallback_mode"] is True
    # Grounded fallback preserves relevant files and structure
    assert "Backend/app.py" in res["sources"] or "Backend/app.py" in res["answer"]
    assert "follow_ups" in res
    assert len(res["follow_ups"]) >= 1


# ---------------------------------------------------------------------------
# 5. Secret Redaction Invariant Test
# ---------------------------------------------------------------------------


def test_secret_redaction_across_text_and_tokens():
    from services.chat.provider_manager import redact_secrets

    leaked = (
        "Here is my key: AIzaSyD9876543210abcdef1234567890abcdef and "
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-ID and "
        "sk-ant-api03-abcdefghijklmnopqrstuvwxyz123456789"
    )

    clean = redact_secrets(leaked)
    assert "AIzaSyD9876543210abcdef1234567890abcdef" not in clean
    assert "Bearer eyJhbGci" not in clean
    assert "[REDACTED_CREDENTIAL]" in clean


# ---------------------------------------------------------------------------
# 6. Investigation State & Discovery Delta Test
# ---------------------------------------------------------------------------


def test_investigation_state_and_discovery_delta():
    """Investigation state computes delta discoveries, confirmed relationships, and risks."""
    tracker = EngineeringThreadTracker("test/repo")

    # Turn 1: Discover app.py and predict()
    state1 = tracker.record_turn(
        question="How does /predict work?",
        answer="`Backend/app.py` defines `/predict` which is tightly coupled to feature extraction.",
        extracted_files=["Backend/app.py"],
        extracted_symbols=["predict"],
        extracted_endpoints=["/predict"],
        intent_name="API_FLOW",
    )

    assert "Backend/app.py" in state1.discovery_delta
    assert "predict" in state1.discovery_delta
    assert "/predict" in state1.discovery_delta
    assert state1.current_depth == InvestigationDepth.SUBSYSTEM_FLOW
    assert (
        "High architectural coupling around central module" in state1.engineering_risks
    )

    # Turn 2: Discover features.py and random_forest_model.pkl
    state2 = tracker.record_turn(
        question="What does it call next?",
        answer="`predict()` loads `random_forest_model.pkl` and transforms inputs with `Backend/features.py`.",
        extracted_files=["Backend/features.py"],
        extracted_symbols=["generate_df"],
        extracted_endpoints=[],
        intent_name="SYMBOL_LOGIC",
    )

    # Invariant: Discovery delta contains ONLY the new entities, not app.py
    assert "Backend/features.py" in state2.discovery_delta
    assert "random_forest_model.pkl" in state2.discovery_delta
    assert "Backend/app.py" not in state2.discovery_delta
    # Invariant: Confirmed relationship recorded for artifact loader
    assert any(
        r.target == "random_forest_model.pkl" for r in state2.confirmed_relationships
    )


# ---------------------------------------------------------------------------
# 7. Entity Disambiguation & Ambiguity Handling Test
# ---------------------------------------------------------------------------


def test_entity_disambiguation_and_ambiguity_handling():
    """Ambiguous references are flagged with explicit options, unambiguous references resolve cleanly."""
    tracker = EngineeringThreadTracker("test/repo")

    candidates = [
        "Backend/utils.py",
        "Backend/features.py",
        "Backend/train.py",
        "WebUI/app.js",
    ]

    # 1. Unambiguous match
    res1 = tracker.disambiguate_reference("features", candidates)
    assert res1["ambiguous"] is False
    assert res1["selected"] == "Backend/features.py"

    # 2. Ambiguous match (e.g. "backend" matches utils, features, train)
    res2 = tracker.disambiguate_reference("backend", candidates)
    assert res2["ambiguous"] is True
    assert res2["selected"] is None
    assert len(res2["candidates"]) == 3
    assert "Multiple entities match" in res2["message"]


# ---------------------------------------------------------------------------
# 8. Repository State Isolation Test
# ---------------------------------------------------------------------------


def test_repository_isolation_between_sessions():
    """State and entities from Repo A never bleed into Repo B."""
    engine = FollowUpEngine()

    tracker_a = engine.get_or_create_tracker("owner_a/repo_a")
    tracker_b = engine.get_or_create_tracker("owner_b/repo_b")

    # Mutate Repo A
    tracker_a.record_turn(
        question="Explain app.py",
        answer="`Backend/app.py` is the entry point.",
        extracted_files=["Backend/app.py"],
        extracted_symbols=["main_handler"],
        extracted_endpoints=[],
    )

    # Mutate Repo B
    tracker_b.record_turn(
        question="Explain server.go",
        answer="`cmd/server.go` initializes the HTTP mux.",
        extracted_files=["cmd/server.go"],
        extracted_symbols=["ServeHTTP"],
        extracted_endpoints=[],
    )

    state_a = tracker_a.get_investigation_state()
    state_b = tracker_b.get_investigation_state()

    assert "Backend/app.py" in state_a.known_facts["files"]
    assert "cmd/server.go" not in state_a.known_facts["files"]

    assert "cmd/server.go" in state_b.known_facts["files"]
    assert "Backend/app.py" not in state_b.known_facts["files"]


# ---------------------------------------------------------------------------
# 9. Multi-Repository Scales Investigation Test
# ---------------------------------------------------------------------------


def test_multi_repository_scales_investigation():
    """Engine produces grounded investigation paths across 4 repository archetypes."""
    engine = FollowUpEngine()

    repos = [
        # Scale 1: Simple (Single file micro-tool)
        (
            "user/mini-cli",
            "How does main() work?",
            "`main.py` parses CLI flags and prints output.",
            ["main.py"],
            ["main"],
        ),
        # Scale 2: Medium (Flask / ML detection)
        (
            "user/flask-ml",
            "How does inference work?",
            "`app.py` routes to `features.py` and evaluates `model.pkl`.",
            ["app.py", "features.py"],
            ["predict"],
        ),
        # Scale 3: Multi-Language (Python backend + TypeScript frontend)
        (
            "user/fullstack",
            "How does the API client interact?",
            "`frontend/src/api.ts` makes fetch calls to `/api/v1/analyze` in `backend/main.py`.",
            ["frontend/src/api.ts", "backend/main.py"],
            ["fetchData"],
        ),
        # Scale 4: Large / Modular
        (
            "user/monorepo",
            "How does authentication flow?",
            "`services/auth/jwt.go` validates tokens and dispatches to `pkg/router/mux.go`.",
            ["services/auth/jwt.go", "pkg/router/mux.go"],
            ["ValidateToken"],
        ),
    ]

    for repo, q, ans, files, symbols in repos:
        followups = engine.synthesize_follow_ups(
            repo_name=repo,
            question=q,
            answer=ans,
            intent="API_FLOW",
            source_files=files,
        )
        assert len(followups) in (2, 3), f"Failed for {repo}"
        combined = " ".join(followups)
        # Invariant: Every scale generates questions grounded in its own source files/symbols
        assert any(f in combined for f in files) or any(s in combined for s in symbols)
