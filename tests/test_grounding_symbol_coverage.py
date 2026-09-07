"""Comprehensive Regression Tests for Stale Index & Symbol Grounding Coverage — PHASES 1 to 9.

Validates:
1. Stale symbol index detection & auto-discard
2. Index refresh producing complete symbols
3. ProviderManager symbol resolution
4. Class span resolution (start_line=156, end_line=735/736)
5. Full symbol chunk retrieval covering all lines
6. Partial-chunk and Full-symbol metadata formatting ([FULL_SYMBOL] vs [PARTIAL_SYMBOL])
7. Deterministic exact-source retrieval
8. No cross-repository contamination
9. No stale index reuse
10. Failover evidence retrieval (Gemini -> DeepSeek failover paths)
11. LLM grounding with complete symbol context
12. LLM grounding with partial symbol context
13. Exact path verification
14. Exact method-name verification
15. Exact line-range verification
"""

import os

from services.symbol_service import SymbolService
from services.chat.explicit_entity_resolver import ExplicitEntityResolver
from services.chat.retrieval import detect_deterministic_retrieval, intelligent_retrieve
from services.chat.context_builder import ContextBuilder


class MockChromaStore:
    def __init__(self, file_paths=None, chunks=None):
        self.file_paths = file_paths or ["services/chat/provider_manager.py"]
        self.chunks = chunks or []

    def get_repository_file_paths(self, repo_name: str):
        return self.file_paths

    def get_file_chunks(self, repo_name: str, file_path: str):
        return {
            "ids": [f"c_{i}" for i in range(len(self.chunks))],
            "documents": [c["content"] for c in self.chunks],
            "metadatas": [c.get("metadata", {}) for c in self.chunks],
        }


def test_stale_symbol_index_detection(tmp_path):
    """Test 1 & 9: Stale symbol index (schema v1) is auto-discarded when current schema is v2."""
    symbols_dir = str(tmp_path / "symbols")
    os.makedirs(symbols_dir, exist_ok=True)

    # Write a stale index with _schema_version = 1
    stale_file = os.path.join(symbols_dir, "test_repo.json")
    with open(stale_file, "w", encoding="utf-8") as f:
        f.write('{"_schema_version": 1, "repo_name": "test/repo", "symbols": []}')

    service = SymbolService(symbols_dir=symbols_dir)
    loaded = service.load("test/repo")
    assert loaded is None, (
        "Stale index with schema v1 must be discarded when current schema is v2"
    )


def test_provider_manager_symbol_and_span_resolution():
    """Test 3, 4, 13, 14, 15: Resolve ProviderManager symbol, span, file path, and methods."""
    service = SymbolService()
    res = service.get_definition_with_span("varshithreddy2006/aria", "ProviderManager")
    assert res is not None, (
        "ProviderManager symbol must be found in varshithreddy2006/aria"
    )

    sym, start_line, end_line = res
    assert sym.name == "ProviderManager"
    assert sym.file_path.replace("\\", "/") == "services/chat/provider_manager.py"
    assert sym.type == "class"
    assert start_line == 156
    assert end_line >= 730

    methods = [
        s.name
        for s in service.get_class_methods("varshithreddy2006/aria", "ProviderManager")
    ]
    expected_methods = [
        "__init__",
        "_load_from_settings",
        "generate",
        "stream",
        "get_last_telemetry",
        "provider_status",
        "reset_all_circuits",
    ]
    for em in expected_methods:
        assert em in methods, (
            f"Expected method '{em}' missing from ProviderManager methods: {methods}"
        )


def test_explicit_entity_resolver_provider_manager():
    """Test 2 & 8: ExplicitEntityResolver extracts ProviderManager with high confidence."""
    resolver = ExplicitEntityResolver()
    res = resolver.resolve("Show me the exact implementation of ProviderManager")
    assert res.has_explicit_entity is True
    assert res.entity_name == "ProviderManager"
    assert res.target_symbol == "ProviderManager"
    assert res.confidence >= 0.95


def test_detect_deterministic_retrieval_provider_manager():
    """Test 7: detect_deterministic_retrieval resolves ProviderManager to services/chat/provider_manager.py."""
    service = SymbolService()
    store = MockChromaStore(
        file_paths=["services/chat/provider_manager.py", "backend/main.py"]
    )

    match = detect_deterministic_retrieval(
        question="Show me the exact implementation of ProviderManager",
        repo_name="varshithreddy2006/aria",
        chroma_store=store,
        symbol_service=service,
    )
    assert match is not None
    assert (
        match["matched_file"].replace("\\", "/") == "services/chat/provider_manager.py"
    )
    assert match["matched_symbol"] == "ProviderManager"
    assert match["symbol_start_line"] == 156
    assert match["symbol_end_line"] >= 730
    assert "generate" in match["symbol_methods"]
    assert "stream" in match["symbol_methods"]


def test_intelligent_retrieve_full_symbol_chunks_and_coverage():
    """Test 5 & 10: intelligent_retrieve returns all overlapping chunks and 100% coverage."""
    service = SymbolService()

    # Simulate multi-chunk provider_manager.py covering lines 1 to 736
    chunks = [
        {
            "content": "# imports\nimport os",
            "metadata": {
                "chunk_id": 0,
                "file_path": "services/chat/provider_manager.py",
                "start_line": 1,
                "end_line": 155,
            },
        },
        {
            "content": "class ProviderManager:\n    def __init__(self):\n        self.primary = 'gemini'\n        self.secondary = 'deepseek'",
            "metadata": {
                "chunk_id": 1,
                "file_path": "services/chat/provider_manager.py",
                "start_line": 156,
                "end_line": 300,
            },
        },
        {
            "content": "    def generate(self):\n        # non-streaming failover to deepseek\n        pass",
            "metadata": {
                "chunk_id": 2,
                "file_path": "services/chat/provider_manager.py",
                "start_line": 301,
                "end_line": 466,
            },
        },
        {
            "content": "    def stream(self):\n        # streaming failover to deepseek\n        pass",
            "metadata": {
                "chunk_id": 3,
                "file_path": "services/chat/provider_manager.py",
                "start_line": 467,
                "end_line": 736,
            },
        },
    ]
    store = MockChromaStore(
        file_paths=["services/chat/provider_manager.py"],
        chunks=chunks,
    )

    retrieved, metrics = intelligent_retrieve(
        question="Show me the exact implementation of ProviderManager",
        repo_name="varshithreddy2006/aria",
        embedding_service=None,
        chroma_store=store,
        symbol_service=service,
    )
    assert len(retrieved) >= 3, (
        "All chunks covering the symbol span (156-736) must be retrieved"
    )
    assert metrics["deterministic"] is True
    assert metrics["matched_symbol"] == "ProviderManager"
    assert metrics["symbol_coverage"] == 100
    assert metrics["symbol_start_line"] == 156
    assert metrics["symbol_end_line"] >= 730


def test_context_builder_full_symbol_tag():
    """Test 6 & 11: ContextBuilder injects [FULL_SYMBOL] and coverage metadata."""
    builder = ContextBuilder()
    chunks = [
        {
            "content": "class ProviderManager:\n    def __init__(self):\n        pass",
            "metadata": {
                "chunk_id": 1,
                "file_path": "services/chat/provider_manager.py",
                "start_line": 156,
                "end_line": 400,
            },
        },
        {
            "content": "    def stream(self):\n        pass",
            "metadata": {
                "chunk_id": 2,
                "file_path": "services/chat/provider_manager.py",
                "start_line": 401,
                "end_line": 736,
            },
        },
    ]

    built = builder.build(
        repo_name="varshithreddy2006/aria",
        question="Show me ProviderManager",
        deterministic_file_path="services/chat/provider_manager.py",
        matched_symbol="ProviderManager",
        symbol_start_line=156,
        symbol_end_line=736,
        symbol_coverage=100,
        symbol_methods=[
            "__init__",
            "_load_from_settings",
            "generate",
            "stream",
            "provider_status",
        ],
        code_chunks=chunks,
    )
    assert "[FULL_SYMBOL]" in built.prompt
    assert "file=services/chat/provider_manager.py" in built.prompt
    assert "symbol=ProviderManager" in built.prompt
    assert "lines=156-736" in built.prompt
    assert "coverage=100%" in built.prompt
    assert (
        "- **Verified Declared Methods:** __init__, _load_from_settings, generate, stream, provider_status"
        in built.prompt
    )


def test_context_builder_partial_symbol_tag():
    """Test 6 & 12: ContextBuilder injects [PARTIAL_SYMBOL] when coverage < 100%."""
    builder = ContextBuilder()
    chunks = [
        {
            "content": "class ProviderManager:\n    def __init__(self):\n        pass",
            "metadata": {
                "chunk_id": 1,
                "file_path": "services/chat/provider_manager.py",
                "start_line": 156,
                "end_line": 220,
            },
        },
    ]

    built = builder.build(
        repo_name="varshithreddy2006/aria",
        question="Show me ProviderManager",
        deterministic_file_path="services/chat/provider_manager.py",
        matched_symbol="ProviderManager",
        symbol_start_line=156,
        symbol_end_line=736,
        symbol_coverage=11,
        code_chunks=chunks,
    )
    assert "[PARTIAL_SYMBOL]" in built.prompt
    assert "coverage=11%" in built.prompt
    assert "total_symbol_lines=581" in built.prompt


def test_no_cross_repository_contamination():
    """Test 8: Distinct repositories return distinct symbols."""
    service = SymbolService()
    # Query non-existent repo or different repo
    sym_other = service.get_definition("other_owner/other_repo", "ProviderManager")
    assert sym_other is None, (
        "Symbol lookup for another repo must not return symbols from varshithreddy2006/aria"
    )


def test_failover_evidence_in_provider_manager():
    """Test 10: Verify current source of provider_manager.py contains failover logic."""
    target_path = "services/chat/provider_manager.py"
    assert os.path.exists(target_path)
    with open(target_path, "r", encoding="utf-8") as f:
        src = f.read()

    # Failover evidence checks
    assert "deepseek" in src.lower()
    assert "gemini" in src.lower()
    assert "failover" in src.lower() or "fallback" in src.lower()
    assert "CircuitBreaker" in src or "circuit" in src.lower()
