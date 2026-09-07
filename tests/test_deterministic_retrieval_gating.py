"""Regression tests for deterministic retrieval symbol gating.

Verifies:
1. Conversational queries with common verbs do NOT hijack deterministic symbol retrieval.
2. Explicit symbols, file paths, and function syntax STILL resolve deterministically.
3. Common code verbs (handle, process, route, build, execute, dispatch, run, manage, support, work, use)
   do not hijack broad conversational questions.
4. Nonexistent file protections are strictly preserved.
"""

import pytest

from services.chat.explicit_entity_resolver import ExplicitEntityResolver
from services.chat.retrieval import detect_deterministic_retrieval
from services.symbol_service import SymbolService


class MockChromaStore:
    def __init__(self, file_paths):
        self._paths = file_paths

    def get_repository_file_paths(self, repo_name):
        return list(self._paths)

    def get(self, include=None, where=None):
        metas = []
        for p in self._paths:
            metas.append({"file_path": p, "language": "python", "chunk_id": 0})
        return {"metadatas": metas}


@pytest.fixture
def repo_env():
    file_paths = [
        "services/chat/provider_manager.py",
        "services/chat/retrieval.py",
        "services/chat/retrieval_pipeline.py",
        "services/chat/context_builder.py",
        "services/llm/gemini_provider.py",
        "services/llm/deepseek_provider.py",
        "backend/main.py",
        "frontend/src/pages/api/[...path].ts",
    ]
    store = MockChromaStore(file_paths)
    symbol_service = SymbolService()
    return store, symbol_service


def test_conversational_queries_with_common_verbs_do_not_hijack_symbols(repo_env):
    """Test 1: Conversational queries with common verbs avoid deterministic symbol hijacking."""
    store, symbol_service = repo_env
    repo_name = "varshithreddy2006/aria"

    queries = [
        "How does ARIA handle LLM provider failures and failover?",
        "Where do we build the prompt context for LLM?",
        "How do we route chat queries?",
    ]

    for q in queries:
        match = detect_deterministic_retrieval(
            question=q,
            repo_name=repo_name,
            chroma_store=store,
            symbol_service=symbol_service,
            intent_name="GENERAL_QA",
        )
        assert match is None, (
            f"Query '{q}' incorrectly matched deterministically: {match}"
        )


def test_explicit_symbol_queries_still_match_deterministically(repo_env):
    """Test 2: Explicit symbol, file path, and function syntax resolve deterministically."""
    store, symbol_service = repo_env
    repo_name = "varshithreddy2006/aria"

    # A. Explicit file path
    m_file = detect_deterministic_retrieval(
        question="Explain services/chat/provider_manager.py",
        repo_name=repo_name,
        chroma_store=store,
        symbol_service=symbol_service,
        intent_name="FILE_EXPLANATION",
    )
    assert m_file is not None
    assert (
        m_file["matched_file"].replace("\\", "/") == "services/chat/provider_manager.py"
    )
    assert m_file["match_type"] == "path"

    # B. Explicit class symbol
    m_sym1 = detect_deterministic_retrieval(
        question="Where is ProviderManager actually defined?",
        repo_name=repo_name,
        chroma_store=store,
        symbol_service=symbol_service,
        intent_name="SYMBOL",
    )
    assert m_sym1 is not None
    assert (
        m_sym1["matched_file"].replace("\\", "/") == "services/chat/provider_manager.py"
    )
    assert m_sym1["matched_symbol"] == "ProviderManager"

    # C. Short explain symbol
    m_sym2 = detect_deterministic_retrieval(
        question="Explain ProviderManager",
        repo_name=repo_name,
        chroma_store=store,
        symbol_service=symbol_service,
        intent_name="SYMBOL",
    )
    assert m_sym2 is not None
    assert (
        m_sym2["matched_file"].replace("\\", "/") == "services/chat/provider_manager.py"
    )

    # D. Explicit function with parentheses
    resolver = ExplicitEntityResolver()
    res_func = resolver.resolve("Explain get_provider()")
    assert res_func.has_explicit_entity is True
    assert res_func.entity_name == "get_provider"
    assert res_func.entity_type == "FUNCTION"


def test_common_verbs_do_not_hijack_broad_conversational_queries(repo_env):
    """Test 3: Broad queries using common verbs (handle, process, route, build, etc.) do not hijack."""
    store, symbol_service = repo_env
    repo_name = "varshithreddy2006/aria"

    common_verb_queries = [
        "How do we handle API exceptions during streaming?",
        "Can you explain how we process incoming chat streams?",
        "Where do we route different types of user questions?",
        "How do we build the context before calling the LLM?",
        "How do we execute vector searches against Qdrant?",
        "How do we dispatch requests across background workers?",
        "How do we run unit and integration tests?",
        "How do we manage conversation state across turns?",
        "Do we support streaming for DeepSeek?",
        "How does the retrieval pipeline work under high load?",
        "Which LLM providers can we use for chat?",
    ]

    for q in common_verb_queries:
        match = detect_deterministic_retrieval(
            question=q,
            repo_name=repo_name,
            chroma_store=store,
            symbol_service=symbol_service,
            intent_name="CONCEPTUAL",
        )
        assert match is None, (
            f"Query '{q}' unexpectedly triggered deterministic retrieval: {match}"
        )


def test_nonexistent_file_rejection(repo_env):
    """Test 4: Nonexistent files are deterministically rejected with not_found=True."""
    store, symbol_service = repo_env
    repo_name = "varshithreddy2006/aria"

    nonexistent = [
        "Explain infrastructure/llm/router.py",
        "Where is services/chat/nonexistent_provider.py defined?",
    ]

    for q in nonexistent:
        match = detect_deterministic_retrieval(
            question=q,
            repo_name=repo_name,
            chroma_store=store,
            symbol_service=symbol_service,
            intent_name="FILE_EXPLANATION",
        )
        assert match is not None, f"Query '{q}' should have matched nonexistent file"
        assert match.get("not_found") is True
        assert match["matched_file"] is None


def test_explicit_backtick_and_snake_case_resolution():
    """Test 5: Explicit backticked tokens and snake_case functions are properly resolved."""
    resolver = ExplicitEntityResolver()

    # Backticked symbol
    res_tick = resolver.resolve("What does `handle` do in the API?")
    assert res_tick.has_explicit_entity is True
    assert res_tick.entity_name == "handle"
    assert res_tick.entity_type == "SYMBOL"

    # PascalCase class
    res_cls = resolver.resolve("Show me ConversationContext implementation")
    assert res_cls.has_explicit_entity is True
    assert res_cls.entity_name == "ConversationContext"
    assert res_cls.entity_type == "CLASS"

    # Suffix matching
    res_mgr = resolver.resolve("Where is GeminiProvider configured?")
    assert res_mgr.has_explicit_entity is True
    assert res_mgr.entity_name == "GeminiProvider"

    # Snake-case function
    res_snake = resolver.resolve("Where is intelligent_retrieve defined?")
    assert res_snake.has_explicit_entity is True
    assert res_snake.entity_name == "intelligent_retrieve"
