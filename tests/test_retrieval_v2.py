"""Repository Chat v2 — comprehensive test suite (Phase 14).

Tests cover:
  - Intent detection (all 9 intents)
  - Intent routing (structured intelligence dispatch)
  - Lockfile exclusion (tier weights)
  - Asymmetric BGE query prefix
  - Reranking and deduplication
  - Conversation memory (pronoun resolution, session TTL)
  - Provider manager (circuit breaker, fallback, streaming retry safety)
  - Fallback rendering (no raw code dumps)
  - Observability (structured trace emission)
  - RetrievalPipeline end-to-end (mocked services)
  - Backward compatibility (RetrievalService shim)
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from typing import AsyncIterator

from services.chat.intent_detector import RuleBasedIntentDetector, Intent, IntentResult
from services.chat.retrieval import (
    _get_tier_weight,
    should_skip_indexing,
    build_query_text,
    _BGE_QUERY_PREFIX,
    _token_overlap_score,
    _content_hash,
    intelligent_retrieve,
)
from services.chat.conversation_memory import ConversationMemoryStore
from services.chat.provider_manager import (
    ProviderManager,
    ProviderEntry,
    CircuitBreaker,
    CircuitState,
)
from services.chat.fallback_renderer import (
    render_fallback,
    render_mid_stream_termination,
)
from services.chat.observability import ChatObservability, PipelineTrace
from services.chat.context_builder import ContextBuilder
from services.chat.retrieval_pipeline import RetrievalPipeline
from services.retrieval_service import RetrievalService
from services.chat.intent_router import IntentRouter


class TestIntentDetector:
    def setup_method(self):
        self.detector = RuleBasedIntentDetector()

    def test_architecture_intent(self):
        r = self.detector.detect("Give me an architecture overview of this codebase")
        assert r.intent == Intent.ARCHITECTURE
        assert r.confidence >= 0.8

    def test_circular_dependency_intent(self):
        r = self.detector.detect("Are there any circular dependencies?")
        assert r.intent == Intent.CIRCULAR_DEPENDENCY

    def test_api_surface_intent(self):
        r = self.detector.detect("List all API endpoints and exported symbols")
        assert r.intent == Intent.API_SURFACE

    def test_call_graph_intent(self):
        r = self.detector.detect("Who calls the UserService.authenticate method?")
        assert r.intent == Intent.CALL_GRAPH

    def test_symbol_intent(self):
        r = self.detector.detect("Where is UserService defined?")
        assert r.intent == Intent.SYMBOL

    def test_reading_order_intent(self):
        r = self.detector.detect(
            "What is the recommended reading order for a new developer?"
        )
        assert r.intent == Intent.READING_ORDER

    def test_impact_analysis_intent(self):
        r = self.detector.detect(
            "What is the blast radius if I change the AuthService?"
        )
        assert r.intent == Intent.IMPACT_ANALYSIS

    def test_general_qa_intent(self):
        r = self.detector.detect("How does the caching layer work?")
        assert r.intent == Intent.GENERAL_QA

    def test_unknown_intent_empty(self):
        r = self.detector.detect("")
        assert r.intent == Intent.UNKNOWN
        assert r.confidence == 0.0

    def test_entity_extraction(self):
        r = self.detector.detect(
            "Explain how UserService and AuthManager work together"
        )
        assert "UserService" in r.entities or "AuthManager" in r.entities

    def test_unknown_intent_random(self):
        r = self.detector.detect("hello there")
        # Should not crash and should return a valid intent
        assert r.intent in list(Intent)


# ---------------------------------------------------------------------------
# Lockfile / Tier Weight Exclusion
# ---------------------------------------------------------------------------


class TestTierWeights:
    def test_lockfile_excluded(self):
        assert _get_tier_weight("package-lock.json") == 0.0
        assert _get_tier_weight("pnpm-lock.yaml") == 0.0
        assert _get_tier_weight("yarn.lock") == 0.0
        assert _get_tier_weight("poetry.lock") == 0.0
        assert _get_tier_weight("Cargo.lock") == 0.0

    def test_node_modules_excluded(self):
        assert _get_tier_weight("node_modules/lodash/index.js") == 0.0

    def test_dist_excluded(self):
        assert _get_tier_weight("frontend/dist/bundle.js") == 0.0

    def test_binary_excluded(self):
        assert _get_tier_weight("assets/logo.png") == 0.0
        assert _get_tier_weight("lib/native.so") == 0.0

    def test_tier1_source_code(self):
        assert _get_tier_weight("backend/services/auth.py") == 1.0
        assert _get_tier_weight("services/user_service.py") == 1.0
        assert _get_tier_weight("frontend/src/components/App.tsx") == 1.0

    def test_tier2_docs(self):
        assert _get_tier_weight("README.md") == 0.6
        assert _get_tier_weight("docs/architecture.md") == 0.6

    def test_tier3_config(self):
        assert _get_tier_weight("requirements.txt") == 0.2
        assert _get_tier_weight("pyproject.toml") == 0.2
        assert _get_tier_weight("package.json") == 0.2

    def test_should_skip_indexing(self):
        assert should_skip_indexing("package-lock.json") is True
        assert should_skip_indexing("backend/api.py") is False


# ---------------------------------------------------------------------------
# Asymmetric BGE Query Prefix
# ---------------------------------------------------------------------------


class TestAsymmetricEmbeddings:
    def test_query_prefix_applied(self):
        q = "How does caching work?"
        result = build_query_text(q)
        assert result.startswith(_BGE_QUERY_PREFIX)
        assert q in result

    def test_query_prefix_not_double_applied(self):
        q = "How does caching work?"
        result = build_query_text(q)
        # Should not double-prefix
        assert result.count(_BGE_QUERY_PREFIX) == 1


# ---------------------------------------------------------------------------
# Reranking and Deduplication
# ---------------------------------------------------------------------------


class TestReranking:
    def test_token_overlap_exact_match(self):
        score = _token_overlap_score(
            "UserService authentication", "UserService handles authentication"
        )
        assert score > 0.5

    def test_token_overlap_no_match(self):
        score = _token_overlap_score("UserService", "def calculate_tax(): pass")
        assert score < 0.3

    def test_token_overlap_empty_query(self):
        score = _token_overlap_score("", "some content")
        assert score == 0.0

    def test_content_hash_identical(self):
        h1 = _content_hash("def foo(): pass")
        h2 = _content_hash("def foo(): pass")
        assert h1 == h2

    def test_content_hash_different(self):
        h1 = _content_hash("def foo(): pass")
        h2 = _content_hash("def bar(): pass")
        assert h1 != h2

    def test_content_hash_whitespace_normalised(self):
        h1 = _content_hash("  def foo(): pass  ")
        h2 = _content_hash("def foo(): pass")
        assert h1 == h2


# ---------------------------------------------------------------------------
# Conversation Memory
# ---------------------------------------------------------------------------


class TestConversationMemory:
    def setup_method(self):
        self.store = ConversationMemoryStore()

    def test_create_session(self):
        session = self.store.get_or_create("owner/repo", "s1")
        assert session.repo_name == "owner/repo"
        assert session.session_id == "s1"

    def test_same_session_returned(self):
        s1 = self.store.get_or_create("owner/repo", "s1")
        s2 = self.store.get_or_create("owner/repo", "s1")
        assert s1 is s2

    def test_different_sessions_isolated(self):
        s1 = self.store.get_or_create("owner/repo", "s1")
        s2 = self.store.get_or_create("owner/repo", "s2")
        assert s1 is not s2

    def test_pronoun_resolution_it(self):
        session = self.store.get_or_create("owner/repo", "pronoun_test")
        session.update_context(entities=["UserService"], files=[], intent="SYMBOL")
        resolved = session.resolve_pronouns("What calls it?")
        assert "UserService" in resolved

    def test_pronoun_no_entity_no_crash(self):
        session = self.store.get_or_create("owner/repo", "no_entity")
        result = session.resolve_pronouns("What calls it?")
        # Should return question unchanged without crashing
        assert isinstance(result, str)

    def test_add_turn_bounded(self):
        session = self.store.get_or_create("owner/repo", "bounded")
        for i in range(25):
            session.add_turn("user", f"question {i}")
        assert len(session.turns) <= 20

    def test_clear_session(self):
        self.store.get_or_create("owner/repo", "to_clear")
        self.store.clear_session("owner/repo", "to_clear")
        # New session should be created (not the same object)
        s = self.store.get_or_create("owner/repo", "to_clear")
        assert len(s.turns) == 0

    def test_entity_tracking_deduplication(self):
        session = self.store.get_or_create("owner/repo", "entity_dedup")
        session.update_context(["UserService", "AuthManager"], [], "SYMBOL")
        session.update_context(["UserService"], [], "SYMBOL")
        assert session.last_entities.count("UserService") == 1


# ---------------------------------------------------------------------------
# Provider Manager — circuit breaker and streaming retry safety
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    def test_initial_state_closed(self):
        cb = CircuitBreaker("test")
        assert cb.state == CircuitState.CLOSED

    def test_opens_after_threshold(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_not_allowed_when_open(self):
        cb = CircuitBreaker("test", failure_threshold=1)
        cb.record_failure()
        assert not cb.is_allowed()

    def test_reset_clears_state(self):
        cb = CircuitBreaker("test", failure_threshold=1)
        cb.record_failure()
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.is_allowed()

    def test_success_closes_circuit(self):
        cb = CircuitBreaker("test", failure_threshold=1)
        cb.record_failure()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED


class TestProviderManagerStreaming:
    """Tests for Phase 9 streaming retry safety."""

    def _make_provider(self, tokens=None, fail_after=0):
        """Create a mock provider that streams tokens or fails."""
        provider = MagicMock()

        async def fake_stream(*args, **kwargs) -> AsyncIterator[str]:
            if tokens:
                for i, t in enumerate(tokens):
                    if fail_after > 0 and i >= fail_after:
                        raise RuntimeError("mid-stream failure")
                    yield t
            else:
                raise RuntimeError("provider unavailable")

        provider.stream = fake_stream
        return provider

    def test_stream_yields_tokens(self):
        p = self._make_provider(tokens=["hello", " ", "world"])
        entry = ProviderEntry(name="test", provider=p, priority=1)
        manager = ProviderManager(providers=[entry])

        async def collect():
            results = []
            async for token, pname in manager.stream("prompt"):
                results.append(token)
            return results

        tokens = asyncio.run(collect())
        assert tokens == ["hello", " ", "world"]

    def test_stream_does_not_retry_after_tokens_yielded(self):
        """Phase 9: mid-stream failure must NOT cause duplicate output."""
        p1 = self._make_provider(tokens=["hello", " "], fail_after=2)
        p2 = self._make_provider(tokens=["DUPLICATE"])
        e1 = ProviderEntry(name="p1", provider=p1, priority=1)
        e2 = ProviderEntry(name="p2", provider=p2, priority=2)
        manager = ProviderManager(providers=[e1, e2])

        async def collect():
            results = []
            try:
                async for token, pname in manager.stream("prompt"):
                    results.append(token)
            except Exception:
                pass
            return results

        tokens = asyncio.run(collect())
        # p2 tokens must NOT appear — no retry after mid-stream
        assert "DUPLICATE" not in tokens

    def test_stream_retries_on_zero_token_failure(self):
        """If 0 tokens yielded, retry with next provider."""
        p1 = self._make_provider(tokens=None)  # fails immediately
        p2 = self._make_provider(tokens=["ok"])
        e1 = ProviderEntry(name="p1", provider=p1, priority=1)
        e2 = ProviderEntry(name="p2", provider=p2, priority=2)
        manager = ProviderManager(providers=[e1, e2])

        async def collect():
            results = []
            async for token, pname in manager.stream("prompt"):
                results.append(token)
            return results

        tokens = asyncio.run(collect())
        assert "ok" in tokens


# ---------------------------------------------------------------------------
# Fallback Rendering — no raw code dumps
# ---------------------------------------------------------------------------


class TestFallbackRenderer:
    def test_fallback_no_raw_code_dump(self):
        chunks = [
            {
                "content": "x" * 2000,  # large chunk
                "metadata": {"file_path": "backend/service.py"},
            }
        ]
        result = render_fallback(
            "How does it work?", "", chunks, ["backend/service.py"]
        )
        # Must NOT dump 2000 chars of raw code
        assert "x" * 100 not in result

    def test_fallback_shows_relevant_files(self):
        chunks = [
            {
                "content": "def foo(): pass",
                "metadata": {"file_path": "services/auth.py"},
            }
        ]
        result = render_fallback("explain auth", "", chunks, ["services/auth.py"])
        assert "services/auth.py" in result

    def test_fallback_shows_structured_intelligence(self):
        intelligence = "## Circular Dependencies\n✅ No cycles detected."
        result = render_fallback("any cycles?", intelligence, [], [])
        assert "Circular Dependencies" in result

    def test_fallback_no_provider_name_exposed(self):
        result = render_fallback("question", "", [], [])
        assert "deepseek" not in result.lower()
        assert "gemini" not in result.lower()
        assert "nvidia" not in result.lower()

    def test_mid_stream_termination_message(self):
        msg = render_mid_stream_termination(tokens_yielded=10)
        assert "incomplete" in msg.lower() or "unavailable" in msg.lower()


# ---------------------------------------------------------------------------
# Observability — trace emission
# ---------------------------------------------------------------------------


class TestObservability:
    def test_emit_does_not_raise(self):
        obs = ChatObservability()
        trace = PipelineTrace(repo_name="owner/repo", session_id="test")
        trace.intent = "GENERAL_QA"
        trace.provider_used = "gemini"
        trace.finish()
        # Should log without exception
        obs.emit(trace)

    def test_trace_finish_sets_total_ms(self):
        import time

        trace = PipelineTrace(repo_name="owner/repo")
        time.sleep(0.01)
        trace.finish()
        assert trace.total_ms >= 5.0  # at least 5ms

    def test_trace_from_retrieval_metrics(self):
        trace = PipelineTrace(repo_name="owner/repo")
        metrics = {
            "initial_retrieved": 15,
            "after_exclusion": 12,
            "after_dedup": 10,
            "final_returned": 5,
            "embed_ms": 42.0,
            "search_ms": 80.0,
            "rerank_ms": 3.0,
        }
        trace.from_retrieval_metrics(metrics)
        assert trace.initial_retrieved == 15
        assert trace.final_returned == 5
        assert trace.embed_ms == 42.0


# ---------------------------------------------------------------------------
# Context Builder
# ---------------------------------------------------------------------------


class TestContextBuilder:
    def setup_method(self):
        self.builder = ContextBuilder()

    def test_basic_build(self):
        ctx = self.builder.build(
            repo_name="owner/repo",
            question="How does caching work?",
        )
        assert "owner/repo" in ctx.system_instruction
        assert "How does caching work?" in ctx.prompt
        assert ctx.estimated_tokens > 0

    def test_structured_intelligence_included(self):
        ctx = self.builder.build(
            repo_name="owner/repo",
            question="any cycles?",
            structured_intelligence="## Circular Dependencies\n✅ No cycles.",
        )
        assert "Circular Dependencies" in ctx.prompt

    def test_token_budget_enforced(self):
        # Feed oversized content to test budget trimming
        big_chunk = {
            "content": "x" * 30_000,
            "metadata": {"file_path": "backend/big.py"},
        }
        ctx = self.builder.build(
            repo_name="owner/repo",
            question="test",
            code_chunks=[big_chunk],
        )
        # Should not exceed budget by more than a small margin
        assert ctx.estimated_tokens <= 5500

    def test_lockfile_chunks_excluded_from_code_slot(self):
        chunks = [
            {
                "content": "locked content",
                "metadata": {"file_path": "package-lock.json"},
            },
            {"content": "real code", "metadata": {"file_path": "backend/api.py"}},
        ]
        ctx = self.builder.build(
            repo_name="owner/repo",
            question="test",
            code_chunks=chunks,
        )
        # Lockfile content should be excluded from code slot
        assert "locked content" not in ctx.prompt

    def test_source_files_collected(self):
        chunks = [
            {"content": "code", "metadata": {"file_path": "services/auth.py"}},
            {"content": "code2", "metadata": {"file_path": "models/user.py"}},
        ]
        ctx = self.builder.build("owner/repo", "test", code_chunks=chunks)
        assert "services/auth.py" in ctx.source_files
        assert "models/user.py" in ctx.source_files


# ---------------------------------------------------------------------------
# RetrievalPipeline end-to-end (mocked services)
# ---------------------------------------------------------------------------


def _make_mock_embedding_service():
    svc = MagicMock()
    svc.generate_embedding.return_value = [0.1] * 384
    return svc


def _make_mock_chroma(chunks=None):
    store = MagicMock()
    store.search_repository.return_value = chunks or [
        {
            "content": "def authenticate(user): pass",
            "metadata": {"file_path": "services/auth.py", "chunk_id": 0},
            "distance": 0.2,
        }
    ]
    return store


def _make_mock_provider(response="This is the answer."):
    provider = MagicMock()

    async def fake_generate(*a, **kw):
        return response, "mock_provider"

    async def fake_stream(*a, **kw) -> AsyncIterator:
        for word in response.split():
            yield word + " ", "mock_provider"

    provider.generate = AsyncMock(return_value=(response, "mock_provider"))
    provider.stream = fake_stream
    return provider


class TestRetrievalPipelineE2E:
    def _make_pipeline(self, provider_response="The answer is here."):
        from services.chat.provider_manager import ProviderManager, ProviderEntry

        emb = _make_mock_embedding_service()
        chroma = _make_mock_chroma()
        provider = _make_mock_provider(provider_response)
        entry = ProviderEntry(name="mock", provider=provider, priority=1)
        pm = ProviderManager(providers=[entry])
        memory = ConversationMemoryStore()
        return RetrievalPipeline(
            embedding_service=emb,
            chroma_store=chroma,
            provider_manager=pm,
            memory_store=memory,
        )

    def test_retrieve_returns_answer(self):
        pipeline = self._make_pipeline("This is the auth service.")
        result = asyncio.run(pipeline.retrieve("owner/repo", "How does auth work?"))
        assert "answer" in result
        assert len(result["answer"]) > 0

    def test_retrieve_returns_sources(self):
        pipeline = self._make_pipeline()
        result = asyncio.run(pipeline.retrieve("owner/repo", "How does auth work?"))
        assert "sources" in result
        assert isinstance(result["sources"], list)

    def test_retrieve_stream_yields_sse(self):
        pipeline = self._make_pipeline("Hello world")

        async def collect():
            events = []
            async for sse in pipeline.retrieve_stream("owner/repo", "test question"):
                events.append(sse)
            return events

        events = asyncio.run(collect())
        # All events must be valid SSE format
        for e in events:
            assert e.startswith("data: ")
            data = json.loads(e[6:].strip())
            assert isinstance(data, dict)

    def test_retrieve_stream_done_event(self):
        pipeline = self._make_pipeline("some answer")

        async def collect():
            events = []
            async for sse in pipeline.retrieve_stream("owner/repo", "test"):
                events.append(json.loads(sse[6:].strip()))
            return events

        events = asyncio.run(collect())
        done_events = [e for e in events if e.get("status") == "done"]
        assert len(done_events) == 1
        done = done_events[0]
        assert "sources" in done
        assert "confidence" in done
        assert "fallback_mode" in done

    def test_retrieve_includes_intent(self):
        pipeline = self._make_pipeline()
        result = asyncio.run(
            pipeline.retrieve("owner/repo", "Are there circular dependencies?")
        )
        assert "intent" in result
        assert result["intent"] == "CIRCULAR_DEPENDENCY"


# ---------------------------------------------------------------------------
# Backward compatibility — RetrievalService shim
# ---------------------------------------------------------------------------


class TestRetrievalServiceShim:
    """Verify the shim preserves the v1 public API exactly."""

    def test_instantiation_unchanged(self):
        emb = _make_mock_embedding_service()
        store = _make_mock_chroma()
        svc = RetrievalService(embedding_service=emb, chroma_store=store)
        assert svc is not None

    def test_retrieve_and_answer_returns_dict(self):
        emb = _make_mock_embedding_service()
        store = _make_mock_chroma()

        # Patch the pipeline's provider manager so it doesn't call real LLM
        with patch("services.chat.retrieval_pipeline.ProviderManager") as MockPM:
            instance = MockPM.return_value
            instance.generate = AsyncMock(return_value=("test answer", "mock"))
            svc = RetrievalService(embedding_service=emb, chroma_store=store)
            svc._pipeline = None  # force rebuild with mock
            # Patch at pipeline level
            with patch.object(svc, "_get_pipeline") as mock_get:
                mock_pipeline = MagicMock()
                mock_pipeline.retrieve = AsyncMock(
                    return_value={
                        "answer": "test answer",
                        "sources": ["services/auth.py"],
                        "confidence": 85,
                        "verified": True,
                        "evaluation": {},
                        "intent": "GENERAL_QA",
                        "fallback_mode": False,
                    }
                )
                mock_get.return_value = mock_pipeline
                result = svc.retrieve_and_answer("owner/repo", "test question")

        assert "answer" in result
        assert "sources" in result
        assert "confidence" in result
        assert "verified" in result
        assert "evaluation" in result


# ---------------------------------------------------------------------------
# Intent Router — basic dispatch
# ---------------------------------------------------------------------------


class TestIntentRouter:
    def test_unknown_intent_returns_empty(self):
        router = IntentRouter()
        ir = IntentResult(intent=Intent.UNKNOWN)
        result = router.route("owner/repo", "some question", ir)
        assert not result.has_data

    def test_general_qa_returns_empty(self):
        router = IntentRouter()
        ir = IntentResult(intent=Intent.GENERAL_QA)
        result = router.route("owner/repo", "how does it work", ir)
        assert not result.has_data

    def test_architecture_with_no_service_returns_empty(self):
        router = IntentRouter(architecture_service=None)
        ir = IntentResult(intent=Intent.ARCHITECTURE)
        result = router.route("owner/repo", "architecture overview", ir)
        assert not result.has_data

    def test_architecture_with_summary(self):
        mock_arch = MagicMock()
        mock_summary = MagicMock()
        mock_summary.total_files = 42
        mock_summary.total_dependencies = 18
        mock_summary.entry_points = ["backend/main.py"]
        mock_summary.core_modules = ["services/"]
        mock_summary.high_coupling_modules = []
        mock_arch.get_summary.return_value = mock_summary

        router = IntentRouter(architecture_service=mock_arch)
        ir = IntentResult(intent=Intent.ARCHITECTURE)
        result = router.route("owner/repo", "architecture overview", ir)
        assert result.has_data
        assert "42" in result.structured_context

    def test_router_elapsed_ms_set(self):
        router = IntentRouter()
        ir = IntentResult(intent=Intent.UNKNOWN)
        result = router.route("owner/repo", "test", ir)
        assert result.router_elapsed_ms >= 0


# ---------------------------------------------------------------------------
# File-Aware Retrieval Regression Tests
# ---------------------------------------------------------------------------


class TestFileAwareRetrievalRegression:
    def test_explain_backend_api(self):
        emb = _make_mock_embedding_service()
        mock_collection = MagicMock()

        def fake_get(*args, **kwargs):
            include = kwargs.get("include", [])
            where = kwargs.get("where", {})
            if include == ["metadatas"]:
                return {
                    "metadatas": [
                        {"file_path": "backend/api.py"},
                        {"file_path": "vscode-extension/src/test/api.test.ts"},
                        {"file_path": "tests/test_architecture.py"},
                        {"file_path": "backend/main.py"},
                    ]
                }

            and_filter = where.get("$and", [])
            file_path = None
            for item in and_filter:
                if "file_path" in item:
                    file_path = item["file_path"]

            if file_path:
                return {
                    "ids": [f"{file_path}_chunk_0"],
                    "documents": [f"Content of {file_path}"],
                    "metadatas": [{"file_path": file_path, "chunk_id": 0}],
                }
            return {"ids": [], "documents": [], "metadatas": []}

        mock_collection.get = MagicMock(side_effect=fake_get)
        chroma = MagicMock()
        chroma.collection = mock_collection

        final_chunks, metrics = intelligent_retrieve(
            question="Explain backend/api.py",
            repo_name="owner/repo",
            embedding_service=emb,
            chroma_store=chroma,
            top_k_final=5,
        )

        assert len(final_chunks) > 0
        assert final_chunks[0]["metadata"]["file_path"] == "backend/api.py"

    def test_explain_provider_manager(self):
        emb = _make_mock_embedding_service()
        mock_collection = MagicMock()

        def fake_get(*args, **kwargs):
            include = kwargs.get("include", [])
            where = kwargs.get("where", {})
            if include == ["metadatas"]:
                return {
                    "metadatas": [
                        {"file_path": "services/chat/provider_manager.py"},
                        {"file_path": "tests/test_provider_manager.py"},
                    ]
                }

            and_filter = where.get("$and", [])
            file_path = None
            for item in and_filter:
                if "file_path" in item:
                    file_path = item["file_path"]

            if file_path:
                return {
                    "ids": [f"{file_path}_chunk_0"],
                    "documents": [f"Content of {file_path}"],
                    "metadatas": [{"file_path": file_path, "chunk_id": 0}],
                }
            return {"ids": [], "documents": [], "metadatas": []}

        mock_collection.get = MagicMock(side_effect=fake_get)
        chroma = MagicMock()
        chroma.collection = mock_collection

        final_chunks, metrics = intelligent_retrieve(
            question="Explain provider_manager.py",
            repo_name="owner/repo",
            embedding_service=emb,
            chroma_store=chroma,
            top_k_final=5,
        )

        assert len(final_chunks) > 0
        assert (
            final_chunks[0]["metadata"]["file_path"]
            == "services/chat/provider_manager.py"
        )

    def test_explain_readme(self):
        emb = _make_mock_embedding_service()
        mock_collection = MagicMock()

        def fake_get(*args, **kwargs):
            include = kwargs.get("include", [])
            where = kwargs.get("where", {})
            if include == ["metadatas"]:
                return {
                    "metadatas": [
                        {"file_path": "README.md"},
                        {"file_path": "docs/architecture.md"},
                    ]
                }

            and_filter = where.get("$and", [])
            file_path = None
            for item in and_filter:
                if "file_path" in item:
                    file_path = item["file_path"]

            if file_path:
                return {
                    "ids": [f"{file_path}_chunk_0"],
                    "documents": [f"Content of {file_path}"],
                    "metadatas": [{"file_path": file_path, "chunk_id": 0}],
                }
            return {"ids": [], "documents": [], "metadatas": []}

        mock_collection.get = MagicMock(side_effect=fake_get)
        chroma = MagicMock()
        chroma.collection = mock_collection

        final_chunks, metrics = intelligent_retrieve(
            question="Explain README.md",
            repo_name="owner/repo",
            embedding_service=emb,
            chroma_store=chroma,
            top_k_final=5,
        )

        assert len(final_chunks) > 0
        assert final_chunks[0]["metadata"]["file_path"] == "README.md"

    def test_explain_docker_compose(self):
        emb = _make_mock_embedding_service()
        mock_collection = MagicMock()

        def fake_get(*args, **kwargs):
            include = kwargs.get("include", [])
            where = kwargs.get("where", {})
            if include == ["metadatas"]:
                return {
                    "metadatas": [
                        {"file_path": "docker-compose.yml"},
                        {"file_path": "Dockerfile"},
                    ]
                }

            and_filter = where.get("$and", [])
            file_path = None
            for item in and_filter:
                if "file_path" in item:
                    file_path = item["file_path"]

            if file_path:
                return {
                    "ids": [f"{file_path}_chunk_0"],
                    "documents": [f"Content of {file_path}"],
                    "metadatas": [{"file_path": file_path, "chunk_id": 0}],
                }
            return {"ids": [], "documents": [], "metadatas": []}

        mock_collection.get = MagicMock(side_effect=fake_get)
        chroma = MagicMock()
        chroma.collection = mock_collection

        final_chunks, metrics = intelligent_retrieve(
            question="Explain docker-compose.yml",
            repo_name="owner/repo",
            embedding_service=emb,
            chroma_store=chroma,
            top_k_final=5,
        )

        assert len(final_chunks) > 0
        assert final_chunks[0]["metadata"]["file_path"] == "docker-compose.yml"

    def test_intelligent_retrieve_priorities_and_confidence(self):
        emb = _make_mock_embedding_service()
        mock_collection = MagicMock()

        # We have files in metadata lookup
        all_metadata_files = [
            {"file_path": "backend/api.py"},
            {"file_path": "services/chat/retrieval_pipeline.py"},
            {"file_path": "tests/test_api.py"},
            {"file_path": "build/artifact.js"},
            {"file_path": "README.md"},
            {"file_path": "pyproject.toml"},
        ]

        def fake_get(*args, **kwargs):
            include = kwargs.get("include", [])
            where = kwargs.get("where", {})
            if include == ["metadatas"]:
                return {"metadatas": all_metadata_files}

            and_filter = where.get("$and", [])
            file_path = None
            for item in and_filter:
                if "file_path" in item:
                    file_path = item["file_path"]

            if file_path:
                return {
                    "ids": [f"{file_path}_chunk_0"],
                    "documents": [
                        "class RetrievalPipeline:\n    def run(self):\n        pass"
                    ],
                    "metadatas": [{"file_path": file_path, "chunk_id": 0}],
                }
            return {"ids": [], "documents": [], "metadatas": []}

        mock_collection.get = MagicMock(side_effect=fake_get)
        chroma = MagicMock()
        chroma.collection = mock_collection

        # Mock search repository to return semantic results
        chroma.search_repository = MagicMock(
            return_value=[
                {
                    "id": "backend/api.py_chunk_0",
                    "content": "api gateway endpoints",
                    "metadata": {"file_path": "backend/api.py", "chunk_id": 0},
                    "distance": 0.3,
                },
                {
                    "id": "README.md_chunk_0",
                    "content": "readme doc files",
                    "metadata": {"file_path": "README.md", "chunk_id": 0},
                    "distance": 0.4,
                },
            ]
        )

        # Mock symbol service
        from models.symbol import Symbol

        mock_symbols = [
            Symbol(
                name="RetrievalPipeline",
                type="class",
                file_path="services/chat/retrieval_pipeline.py",
                line_number=10,
                language="python",
            )
        ]

        class MockSymbolIndex:
            def __init__(self, symbols):
                self.symbols = symbols

        class MockSymbolService:
            def load(self, repo_name):
                return MockSymbolIndex(mock_symbols)

        symbol_service = MockSymbolService()

        # Query 1: Exact path match backend/api.py (asks for production file)
        final_chunks, metrics = intelligent_retrieve(
            question="Explain backend/api.py",
            repo_name="owner/repo",
            embedding_service=emb,
            chroma_store=chroma,
            top_k_final=5,
            symbol_service=symbol_service,
        )
        assert len(final_chunks) > 0
        assert final_chunks[0]["metadata"]["file_path"] == "backend/api.py"
        assert final_chunks[0]["metadata"]["why_this_file"] == "Matched exact path"
        assert metrics["confidence"] == 100
        # Tests/generated files must be filtered out
        for c in final_chunks:
            assert "test_api.py" not in c["metadata"]["file_path"]
            assert "artifact.js" not in c["metadata"]["file_path"]

        # Query 2: Exact symbol match (RetrievalPipeline)
        final_chunks, metrics = intelligent_retrieve(
            question="Explain RetrievalPipeline class",
            repo_name="owner/repo",
            embedding_service=emb,
            chroma_store=chroma,
            top_k_final=5,
            symbol_service=symbol_service,
        )
        assert len(final_chunks) > 0
        assert (
            final_chunks[0]["metadata"]["file_path"]
            == "services/chat/retrieval_pipeline.py"
        )
        assert (
            final_chunks[0]["metadata"]["why_this_file"] == "Contains requested symbol"
        )
        assert metrics["confidence"] == 96
        # Exact symbol metadata must be populated
        assert (
            "RetrievalPipeline (class)"
            in final_chunks[0]["metadata"]["matched_symbols"]
        )

        # Query 3: Ask about tests explicitly
        final_chunks, metrics = intelligent_retrieve(
            question="Show me tests in tests/test_api.py",
            repo_name="owner/repo",
            embedding_service=emb,
            chroma_store=chroma,
            top_k_final=5,
            symbol_service=symbol_service,
        )
        assert any(
            c["metadata"]["file_path"] == "tests/test_api.py" for c in final_chunks
        )


class TestDeterministicFileRetrievalSpec:
    def setup_method(self):
        self.emb = _make_mock_embedding_service()
        self.chroma = MagicMock()
        self.mock_collection = MagicMock()
        self.chroma.collection = self.mock_collection

        # Setup mock files in Chroma metadata
        self.all_files = [
            "backend/api.py",
            "vscode-extension/src/test/api.test.ts",
            "tests/test_architecture.py",
            "services/chat/provider_manager.py",
            "tests/test_provider_manager.py",
            "README.md",
            "docker-compose.yml",
            "services/architecture_service.py",
            "out/dist/bundle.js",
        ]

        def fake_get(*args, **kwargs):
            include = kwargs.get("include", [])
            where = kwargs.get("where", {})

            # Fetching list of all unique file paths
            if include == ["metadatas"]:
                return {"metadatas": [{"file_path": f} for f in self.all_files]}

            # Fetching chunks for a specific file path
            and_filter = where.get("$and", []) if where else []
            file_path = None
            for item in and_filter:
                if "file_path" in item:
                    file_path = item["file_path"]

            if file_path:
                # Return chunks out of order to verify sorting is preserved
                return {
                    "ids": [
                        f"{file_path}_chunk_1",
                        f"{file_path}_chunk_0",
                        f"{file_path}_chunk_2",
                    ],
                    "documents": [
                        f"Content of {file_path} chunk 1",
                        f"Content of {file_path} chunk 0",
                        f"Content of {file_path} chunk 2",
                    ],
                    "metadatas": [
                        {"file_path": file_path, "chunk_id": 1, "language": "python"},
                        {"file_path": file_path, "chunk_id": 0, "language": "python"},
                        {"file_path": file_path, "chunk_id": 2, "language": "python"},
                    ],
                }
            return {"ids": [], "documents": [], "metadatas": []}

        self.mock_collection.get = MagicMock(side_effect=fake_get)
        self.chroma.search_repository = MagicMock()  # Should not be called
        self.emb.generate_embedding = MagicMock()  # Should not be called

        # Setup SymbolService mock
        from models.symbol import Symbol

        mock_symbols = [
            Symbol(
                name="ProviderManager",
                type="class",
                file_path="services/chat/provider_manager.py",
                line_number=15,
                language="python",
            ),
            Symbol(
                name="ArchitectureService",
                type="class",
                file_path="services/architecture_service.py",
                line_number=8,
                language="python",
            ),
        ]

        class MockSymbolIndex:
            def __init__(self, symbols):
                self.symbols = symbols

        class MockSymbolService:
            def load(self, repo_name):
                return MockSymbolIndex(mock_symbols)

            def get_definition(self, repo_name, symbol_name):
                for s in mock_symbols:
                    if s.name == symbol_name:
                        return s
                return None

            def get_file_symbols(self, repo_name, file_path):
                return [s for s in mock_symbols if s.file_path == file_path]

        self.symbol_service = MockSymbolService()

    def test_explain_backend_api_path(self):
        chunks, metrics = intelligent_retrieve(
            question="Explain backend/api.py",
            repo_name="owner/repo",
            embedding_service=self.emb,
            chroma_store=self.chroma,
            symbol_service=self.symbol_service,
        )
        # Verify semantic retrieval NOT executed
        self.chroma.search_repository.assert_not_called()
        self.emb.generate_embedding.assert_not_called()

        # Verify only requested file returned
        assert len(chunks) == 3
        for c in chunks:
            assert c["metadata"]["file_path"] == "backend/api.py"

        # Verify chunk order preserved (sorted by chunk_id)
        assert chunks[0]["metadata"]["chunk_id"] == 0
        assert chunks[1]["metadata"]["chunk_id"] == 1
        assert chunks[2]["metadata"]["chunk_id"] == 2

        # Verify confidence is correct
        assert metrics["confidence"] == 100

        # Verify no tests / compiled files
        for c in chunks:
            fp = c["metadata"]["file_path"]
            assert "test" not in fp
            assert "dist" not in fp

    def test_explain_api_filename(self):
        chunks, metrics = intelligent_retrieve(
            question="Explain api.py",
            repo_name="owner/repo",
            embedding_service=self.emb,
            chroma_store=self.chroma,
            symbol_service=self.symbol_service,
        )
        self.chroma.search_repository.assert_not_called()
        self.emb.generate_embedding.assert_not_called()

        assert len(chunks) == 3
        assert chunks[0]["metadata"]["file_path"] == "backend/api.py"
        assert metrics["confidence"] == 98

    def test_explain_provider_manager_filename(self):
        chunks, metrics = intelligent_retrieve(
            question="Explain provider_manager.py",
            repo_name="owner/repo",
            embedding_service=self.emb,
            chroma_store=self.chroma,
            symbol_service=self.symbol_service,
        )
        self.chroma.search_repository.assert_not_called()
        self.emb.generate_embedding.assert_not_called()

        assert len(chunks) == 3
        assert chunks[0]["metadata"]["file_path"] == "services/chat/provider_manager.py"
        assert metrics["confidence"] == 98

    def test_explain_readme(self):
        chunks, metrics = intelligent_retrieve(
            question="Explain README.md",
            repo_name="owner/repo",
            embedding_service=self.emb,
            chroma_store=self.chroma,
            symbol_service=self.symbol_service,
        )
        self.chroma.search_repository.assert_not_called()
        self.emb.generate_embedding.assert_not_called()

        assert len(chunks) == 3
        assert chunks[0]["metadata"]["file_path"] == "README.md"
        assert metrics["confidence"] in (98, 100)

    def test_explain_docker_compose(self):
        chunks, metrics = intelligent_retrieve(
            question="Explain docker-compose.yml",
            repo_name="owner/repo",
            embedding_service=self.emb,
            chroma_store=self.chroma,
            symbol_service=self.symbol_service,
        )
        self.chroma.search_repository.assert_not_called()
        self.emb.generate_embedding.assert_not_called()

        assert len(chunks) == 3
        assert chunks[0]["metadata"]["file_path"] == "docker-compose.yml"
        assert metrics["confidence"] in (98, 100)

    def test_explain_provider_manager_symbol(self):
        chunks, metrics = intelligent_retrieve(
            question="Explain ProviderManager",
            repo_name="owner/repo",
            embedding_service=self.emb,
            chroma_store=self.chroma,
            symbol_service=self.symbol_service,
        )
        self.chroma.search_repository.assert_not_called()
        self.emb.generate_embedding.assert_not_called()

        assert len(chunks) == 3
        assert chunks[0]["metadata"]["file_path"] == "services/chat/provider_manager.py"
        assert metrics["confidence"] == 96

    def test_explain_architecture_service_symbol(self):
        chunks, metrics = intelligent_retrieve(
            question="Explain ArchitectureService",
            repo_name="owner/repo",
            embedding_service=self.emb,
            chroma_store=self.chroma,
            symbol_service=self.symbol_service,
        )
        self.chroma.search_repository.assert_not_called()
        self.emb.generate_embedding.assert_not_called()

        assert len(chunks) == 3
        assert chunks[0]["metadata"]["file_path"] == "services/architecture_service.py"
        assert metrics["confidence"] == 96


class TestPipelineCitationVerification:
    def _pipeline(self, answer: str):
        from services.chat.provider_manager import ProviderEntry, ProviderManager

        provider = MagicMock()
        provider.generate = AsyncMock(return_value=answer)

        async def stream(*_args, **_kwargs):
            for token in answer.split():
                yield token + " "

        provider.stream = stream
        return RetrievalPipeline(
            embedding_service=_make_mock_embedding_service(),
            chroma_store=_make_mock_chroma(),
            provider_manager=ProviderManager(
                providers=[ProviderEntry(name="citation", provider=provider, priority=1)]
            ),
            memory_store=ConversationMemoryStore(),
        )

    def test_grounded_answer_is_verified_after_citation_check(self):
        pipeline = self._pipeline("See backend/api.py:1-10.")
        result = asyncio.run(pipeline.retrieve("owner/repo", "Where is the API?", session_id="grounded"))
        assert result["verified"] is True
        assert result["citation_report"]["citations_valid"] is True

    def test_hallucinated_citation_is_not_verified(self):
        pipeline = self._pipeline("See nonexistent/file.py:1-5.")
        result = asyncio.run(pipeline.retrieve("owner/repo", "Where is the API?", session_id="hallucinated"))
        assert result["verified"] is False
        assert result["citation_report"]["citations_valid"] is False

    def test_stream_terminal_event_includes_verification_state(self):
        pipeline = self._pipeline("See nonexistent/file.py:1-5.")

        async def collect():
            return [json.loads(event[6:].strip()) async for event in pipeline.retrieve_stream("owner/repo", "Where?", session_id="stream")]

        done_event = next(event for event in asyncio.run(collect()) if event.get("status") == "done")
        assert done_event["verified"] is False
        assert done_event["citation_report"]["citations_valid"] is False


class TestGeneratedChatSessions:
    def test_requests_without_session_ids_receive_distinct_sessions(self):
        from backend.routers.chat import ChatRequest

        first = ChatRequest(repo="owner/repo", message="first")
        second = ChatRequest(repo="owner/repo", message="second")
        assert first.session_id != second.session_id
        assert first.session_id != "default"

    def test_unspecified_memory_sessions_are_isolated(self):
        memory = ConversationMemoryStore()
        first = memory.get_or_create("owner/repo")
        second = memory.get_or_create("owner/repo")
        first.update_context(["OnlyFirst"], [], "SYMBOL")

        assert first.session_id != second.session_id
        assert "OnlyFirst" not in second.last_entities
