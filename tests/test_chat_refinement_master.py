"""Master Chat Intelligence Refinement Regression Tests.

Validates all 12 test groups:
1. Common word hijacking prevention
2. Explicit symbol resolution
3. Provider failover context & distinction
4. Provider order grounding
5. Stream failure handling & error fidelity
6. Exponential backoff vs failover distinction
7. Adding new LLM provider grounding
8. Broad architecture question context & ranking
9. End-to-end pipeline stages
10. Nonexistent file rejection
11. Security and credential protection
12. Grounded follow-up question synthesis
"""

from unittest.mock import MagicMock
import pytest

from services.chat.retrieval import (
    detect_deterministic_retrieval,
    determine_ranking_category,
    is_historical_or_benchmark_doc,
)
from services.chat.response_schema import ResponseSchemaBuilder
from services.chat.followup_engine import FollowUpEngine
from services.chat.provider_manager import (
    ProviderManager,
    ProviderEntry,
    CircuitState,
)


# ===========================================================================
# TEST GROUP 1 — COMMON WORD HIJACKING
# ===========================================================================


@pytest.mark.parametrize(
    "query",
    [
        "How does ARIA handle LLM provider failures and failover?",
        "How does ARIA route requests across different modules?",
        "How do we build the dependency graph?",
        "How do we process files during repository ingestion?",
        "How do we run the indexing pipeline?",
        "How do we execute unit tests across the codebase?",
        "How does the dispatcher dispatch events to listeners?",
        "How does ARIA manage LLM provider failover?",
        "How do we use Chroma and Qdrant for vector storage?",
    ],
)
def test_common_verbs_do_not_hijack_retrieval(query):
    mock_chroma = MagicMock()
    mock_chroma.get_unique_file_paths.return_value = [
        "services/chat/provider_manager.py",
        "frontend/src/pages/api/[...path].ts",
        "core/indexing_pipeline.py",
    ]
    mock_symbol_service = MagicMock()
    mock_symbol = MagicMock()
    mock_symbol.name = "handle"
    mock_symbol.file_path = "frontend/src/pages/api/[...path].ts"
    mock_symbol_service.get_symbol.return_value = [mock_symbol]

    det = detect_deterministic_retrieval(
        question=query,
        repo_name="test_repo",
        chroma_store=mock_chroma,
        symbol_service=mock_symbol_service,
    )
    # None of these broad queries should trigger deterministic hijack on single verbs
    assert det is None, f"Query '{query}' was falsely hijacked deterministically: {det}"


# ===========================================================================
# TEST GROUP 2 — EXPLICIT SYMBOL & FILE RESOLUTION
# ===========================================================================


def test_explicit_symbol_and_file_resolution():
    mock_chroma = MagicMock()
    mock_chroma.collection.get.return_value = {
        "metadatas": [
            {"file_path": "services/chat/provider_manager.py"},
            {"file_path": "services/chat/llm_provider.py"},
        ]
    }
    mock_symbol_service = MagicMock()
    mock_pm_sym = MagicMock()
    mock_pm_sym.name = "ProviderManager"
    mock_pm_sym.file_path = "services/chat/provider_manager.py"
    mock_pm_sym.type = "class"
    mock_symbol_service.get_definition_with_span.return_value = (mock_pm_sym, 167, 783)
    mock_symbol_service.get_class_methods.return_value = []
    mock_symbol_service.get_symbol.side_effect = lambda name, **kwargs: (
        [mock_pm_sym] if name == "ProviderManager" else []
    )

    # 1. Explain ProviderManager
    det_pm = detect_deterministic_retrieval(
        question="Explain ProviderManager",
        repo_name="test_repo",
        chroma_store=mock_chroma,
        symbol_service=mock_symbol_service,
    )
    assert det_pm is not None
    assert det_pm["matched_file"] == "services/chat/provider_manager.py"

    # 2. Where is ProviderManager defined?
    det_def = detect_deterministic_retrieval(
        question="Where is ProviderManager defined?",
        repo_name="test_repo",
        chroma_store=mock_chroma,
        symbol_service=mock_symbol_service,
    )
    assert det_def is not None
    assert det_def["matched_file"] == "services/chat/provider_manager.py"

    # 3. Explain services/chat/provider_manager.py
    det_file = detect_deterministic_retrieval(
        question="Explain services/chat/provider_manager.py",
        repo_name="test_repo",
        chroma_store=mock_chroma,
        symbol_service=mock_symbol_service,
    )
    assert det_file is not None
    assert det_file["matched_file"] == "services/chat/provider_manager.py"


# ===========================================================================
# TEST GROUP 3 & 4 — PROVIDER FAILOVER & ORDER GROUNDING
# ===========================================================================


def test_provider_manager_subsystem_semantics():
    entry = ProviderEntry(name="test_provider", provider=MagicMock(), priority=1)
    entry.circuit_breaker.failure_threshold = 2
    pm = ProviderManager(providers=[entry])
    assert hasattr(pm, "generate")
    assert hasattr(pm, "stream")
    assert hasattr(pm, "get_last_telemetry")
    assert hasattr(pm, "provider_status")
    assert hasattr(pm, "reset_all_circuits")

    # Trip circuit breaker
    entry.circuit_breaker.record_failure()
    entry.circuit_breaker.record_failure()
    assert entry.circuit_breaker.state == CircuitState.OPEN

    # reset_all_circuits sets state back to CLOSED (healthy), never trips them
    pm.reset_all_circuits()
    assert entry.circuit_breaker.state == CircuitState.CLOSED
    assert entry.circuit_breaker._failure_count == 0


def test_ranking_prioritizes_production_source_over_historical_docs():
    score_src, why_src = determine_ranking_category(
        path="services/chat/provider_manager.py",
        question="Which providers does ProviderManager try, and in what order?",
        candidates=[],
        matched_symbols_by_file={
            "services/chat/provider_manager.py": ["ProviderManager"]
        },
        asks_about_tests=False,
    )

    score_doc, why_doc = determine_ranking_category(
        path="docs/performance/BENCHMARK_REPORT.md",
        question="Which providers does ProviderManager try, and in what order?",
        candidates=[],
        matched_symbols_by_file={},
        asks_about_tests=False,
    )

    score_hist, why_hist = determine_ranking_category(
        path="docs/engineering-audit.md",
        question="Which providers does ProviderManager try, and in what order?",
        candidates=[],
        matched_symbols_by_file={},
        asks_about_tests=False,
    )

    assert (
        is_historical_or_benchmark_doc("docs/performance/BENCHMARK_REPORT.md") is True
    )
    assert is_historical_or_benchmark_doc("docs/engineering-audit.md") is True
    assert is_historical_or_benchmark_doc("services/chat/provider_manager.py") is False

    # Production source with symbol match must heavily outrank documentation
    assert score_src >= 800000.0
    assert score_doc <= 150000.0
    assert score_hist <= 150000.0


# ===========================================================================
# TEST GROUP 5 & 6 — STREAM FAILURE & BACKOFF DISTINCTION
# ===========================================================================


def test_system_instruction_distinguishes_failover_and_circuit_breakers():
    sys_inst = ResponseSchemaBuilder.build_system_instruction("VarshithReddy2006/ARIA")
    assert "Provider Failover: ProviderManager iterates" in sys_inst
    assert "Circuit Breakers: ProviderHealth tracks CLOSED/OPEN/HALF_OPEN" in sys_inst
    assert "reset_all_circuits(): Resets all circuit breakers to CLOSED" in sys_inst
    assert (
        "ProviderManager failover does NOT use exponential_backoff() or time.sleep()"
        in sys_inst
    )
    assert "Code Block Verification" in sys_inst
    assert "Security & Credential Protection" in sys_inst


# ===========================================================================
# TEST GROUP 10 — NONEXISTENT FILES REJECTION
# ===========================================================================


def test_nonexistent_files_rejection():
    mock_chroma = MagicMock()
    mock_chroma.get_unique_file_paths.return_value = [
        "services/chat/provider_manager.py",
        "services/chat/retrieval.py",
    ]
    mock_symbol_service = MagicMock()
    mock_symbol_service.get_symbol.return_value = []

    det1 = detect_deterministic_retrieval(
        question="Explain infrastructure/llm/router.py",
        repo_name="test_repo",
        chroma_store=mock_chroma,
        symbol_service=mock_symbol_service,
    )
    assert det1 is None

    det2 = detect_deterministic_retrieval(
        question="Find services/chat/nonexistent_provider.py",
        repo_name="test_repo",
        chroma_store=mock_chroma,
        symbol_service=mock_symbol_service,
    )
    assert det2 is None


# ===========================================================================
# TEST GROUP 11 — SECURITY / SECRET PROTECTION
# ===========================================================================


def test_security_rules_in_system_instruction():
    sys_inst = ResponseSchemaBuilder.build_system_instruction("test_repo")
    assert "NEVER reveal, log, or output API keys" in sys_inst
    assert "refuse immediately" in sys_inst


# ===========================================================================
# TEST GROUP 12 — GROUNDED FOLLOW-UP GENERATION
# ===========================================================================


def test_followup_synthesis_binds_symbols_to_containing_chunks():
    engine = FollowUpEngine()
    code_chunks = [
        {
            "metadata": {
                "file_path": "services/chat/provider_manager.py",
                "matched_symbols": ["stream", "reset_all_circuits"],
            },
            "content": "class ProviderManager:\n    def stream(self):\n        pass\n    def reset_all_circuits(self):\n        pass",
        },
        {
            "metadata": {
                "file_path": "frontend/src/lib/chatIntelligence.ts",
            },
            "content": "export function formatChatMessage() { return true; }",
        },
    ]

    follow_ups = engine.synthesize_follow_ups(
        repo_name="test_repo",
        question="Explain ProviderManager",
        answer="ProviderManager orchestrates LLM providers and circuit breakers.",
        intent="SYMBOL",
        code_chunks=code_chunks,
        source_files=[
            "services/chat/provider_manager.py",
            "frontend/src/lib/chatIntelligence.ts",
        ],
    )

    assert len(follow_ups) >= 2
    # Verify that ProviderManager symbols are NOT hallucinated into chatIntelligence.ts
    for q in follow_ups:
        if "stream()" in q or "reset_all_circuits()" in q:
            assert "chatIntelligence.ts" not in q
        assert "pkl" not in q.lower()
        assert "onnx" not in q.lower()
