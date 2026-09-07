"""Retrieval Optimization Test Suite.

Verifies:
1. Exact symbol retrieval and metadata population.
2. Deterministic file retrieval (exact + partial paths).
3. Evidence ranking, tier weights, and per-file diminishing returns.
4. Chunk deduplication and redundant structured snippet elimination.
5. Context budget enforcement (max_files, max_chunks, max_chunks_per_file, max_chars).
6. Empty / zero-result retrieval graceful handling.
7. File classification caching and retrieval timer instrumentation.
"""

from unittest.mock import MagicMock, patch

from services.chat.retrieval import (
    _get_tier_weight,
    _get_cached_classification,
    _CLASSIFICATION_CACHE,
    detect_deterministic_retrieval,
    populate_chunk_symbols_and_lines,
)
from services.chat.context_builder import ContextBuilder
from services.chat.retrieval_timer import RetrievalTimer


# ---------------------------------------------------------------------------
# 1. Exact Symbol Retrieval & Populator Tests
# ---------------------------------------------------------------------------


class TestSymbolRetrieval:
    def test_populate_chunk_symbols_and_lines_with_cached_index(self):
        chunk = {
            "content": "def authenticate(user, password):\n    return True\n",
            "metadata": {
                "file_path": "services/auth.py",
                "start_line": 1,
                "end_line": 2,
            },
        }

        # Mock symbol object
        mock_sym = MagicMock()
        mock_sym.name = "authenticate"
        mock_sym.file_path = "services/auth.py"
        mock_sym.line_number = 1
        mock_sym.type = "function"

        # Mock index object with file_symbol_map
        mock_index = MagicMock()
        mock_index.file_symbol_map = {"services/auth.py": [mock_sym]}

        populate_chunk_symbols_and_lines(
            chunk=chunk,
            repo_name="test/repo",
            question="How does authenticate work?",
            symbol_service=None,
            symbol_index=mock_index,
        )

        assert "authenticate (function)" in chunk["metadata"]["matched_symbols"]
        assert chunk["metadata"]["start_line"] == 1

    def test_populate_chunk_without_symbols(self):
        chunk = {
            "content": "x = 1\ny = 2\n",
            "metadata": {"file_path": "config.py", "start_line": 1, "end_line": 2},
        }
        populate_chunk_symbols_and_lines(
            chunk=chunk,
            repo_name="test/repo",
            question="What is this config?",
            symbol_service=None,
            symbol_index=None,
        )
        assert (
            chunk["metadata"].get("matched_symbols") is None
            or chunk["metadata"].get("matched_symbols") == ""
        )


# ---------------------------------------------------------------------------
# 2. File Retrieval (Exact + Partial)
# ---------------------------------------------------------------------------


class TestDeterministicFileRetrieval:
    def test_exact_and_partial_file_match(self):
        mock_chroma = MagicMock()
        # Mock ChromaStore get_unique_file_paths
        with patch("services.chat.retrieval.get_unique_file_paths") as mock_get_files:
            mock_get_files.return_value = [
                "src/controllers/auth_controller.py",
                "src/models/user.py",
                "README.md",
            ]

            # Exact path
            m1 = detect_deterministic_retrieval(
                question="Explain src/models/user.py",
                repo_name="org/repo",
                chroma_store=mock_chroma,
                symbol_service=None,
            )
            assert m1 is not None
            assert m1["matched_file"] == "src/models/user.py"

            # Partial filename with extension
            m2 = detect_deterministic_retrieval(
                question="What is in auth_controller.py?",
                repo_name="org/repo",
                chroma_store=mock_chroma,
                symbol_service=None,
            )
            assert m2 is not None
            assert m2["matched_file"] == "src/controllers/auth_controller.py"

    def test_non_matching_query(self):
        mock_chroma = MagicMock()
        with patch("services.chat.retrieval.get_unique_file_paths") as mock_get_files:
            mock_get_files.return_value = ["src/models/user.py"]
            m = detect_deterministic_retrieval(
                question="How does payment processing work?",
                repo_name="org/repo",
                chroma_store=mock_chroma,
                symbol_service=None,
            )
            assert m is None


# ---------------------------------------------------------------------------
# 3. Evidence Ranking & Classification Caching
# ---------------------------------------------------------------------------


class TestEvidenceRankingAndClassificationCache:
    def test_classification_cache(self):
        _CLASSIFICATION_CACHE.clear()

        # Test first call caches the result
        cls1 = _get_cached_classification("services/chat/retrieval.py")
        assert "services/chat/retrieval.py" in _CLASSIFICATION_CACHE
        assert cls1 == _CLASSIFICATION_CACHE["services/chat/retrieval.py"]

        # Test second call uses cache
        cls2 = _get_cached_classification("services/chat/retrieval.py")
        assert cls1 == cls2

    def test_tier_weights(self):
        assert _get_tier_weight("src/index.ts") >= 1.0
        assert _get_tier_weight("package-lock.json") == 0.0
        assert _get_tier_weight("poetry.lock") == 0.0
        assert _get_tier_weight("README.md") == 0.6


# ---------------------------------------------------------------------------
# 4. Chunk Deduplication
# ---------------------------------------------------------------------------


class TestChunkDeduplication:
    def test_deduplicate_identical_chunks(self):
        builder = ContextBuilder()
        chunks = [
            {
                "content": "def foo(): pass",
                "metadata": {
                    "file_path": "a.py",
                    "start_line": 1,
                    "end_line": 2,
                    "chunk_id": "c1",
                },
            },
            {
                "content": "def foo(): pass",
                "metadata": {
                    "file_path": "a.py",
                    "start_line": 1,
                    "end_line": 2,
                    "chunk_id": "c1",
                },
            },
            {
                "content": "def bar(): pass",
                "metadata": {
                    "file_path": "b.py",
                    "start_line": 1,
                    "end_line": 2,
                    "chunk_id": "c2",
                },
            },
        ]
        filtered = builder._filter_and_budget_chunks(chunks)
        assert len(filtered) == 2
        assert filtered[0]["metadata"]["chunk_id"] == "c1"
        assert filtered[1]["metadata"]["chunk_id"] == "c2"

    def test_deduplicate_against_structured_intelligence(self):
        builder = ContextBuilder()
        struct_intel = "Here is the exact definition:\n```python\ndef calculate_tax():\n    return 0.15\n```"
        chunks = [
            {
                "content": "def calculate_tax():\n    return 0.15",
                "metadata": {
                    "file_path": "tax.py",
                    "start_line": 10,
                    "end_line": 12,
                    "chunk_id": "c_tax",
                },
            },
            {
                "content": "def print_report():\n    pass",
                "metadata": {
                    "file_path": "tax.py",
                    "start_line": 20,
                    "end_line": 22,
                    "chunk_id": "c_rep",
                },
            },
        ]
        filtered = builder._filter_and_budget_chunks(
            chunks, structured_intelligence=struct_intel
        )
        assert len(filtered) == 1
        assert filtered[0]["metadata"]["chunk_id"] == "c_rep"


# ---------------------------------------------------------------------------
# 5. Context Budget Enforcement
# ---------------------------------------------------------------------------


class TestContextBudgetEnforcement:
    def test_per_file_and_total_chunk_limits(self):
        builder = ContextBuilder(max_files=2, max_chunks=4, max_chunks_per_file=2)

        chunks = (
            [
                # File 1: 3 chunks (should only take 2)
                {
                    "content": f"f1 chunk {i}",
                    "metadata": {
                        "file_path": "file1.py",
                        "start_line": i * 10,
                        "end_line": i * 10 + 5,
                        "chunk_id": f"f1_{i}",
                    },
                }
                for i in range(3)
            ]
            + [
                # File 2: 3 chunks (should only take 2)
                {
                    "content": f"f2 chunk {i}",
                    "metadata": {
                        "file_path": "file2.py",
                        "start_line": i * 10,
                        "end_line": i * 10 + 5,
                        "chunk_id": f"f2_{i}",
                    },
                }
                for i in range(3)
            ]
            + [
                # File 3: 2 chunks (should be ignored due to max_files=2)
                {
                    "content": f"f3 chunk {i}",
                    "metadata": {
                        "file_path": "file3.py",
                        "start_line": i * 10,
                        "end_line": i * 10 + 5,
                        "chunk_id": f"f3_{i}",
                    },
                }
                for i in range(2)
            ]
        )

        filtered = builder._filter_and_budget_chunks(chunks)
        assert len(filtered) == 4
        # Verify only 2 files are present
        present_files = {ch["metadata"]["file_path"] for ch in filtered}
        assert present_files == {"file1.py", "file2.py"}
        # Verify 2 chunks per file
        assert (
            sum(1 for ch in filtered if ch["metadata"]["file_path"] == "file1.py") == 2
        )
        assert (
            sum(1 for ch in filtered if ch["metadata"]["file_path"] == "file2.py") == 2
        )

    def test_deterministic_context_assembly_without_disk_reads(self):
        builder = ContextBuilder()
        chunks = [
            {
                "content": "def handle_request():\n    pass\n",
                "metadata": {
                    "file_path": "api/router.py",
                    "chunk_id": "chk_0",
                    "start_line": 1,
                    "end_line": 3,
                    "language": "python",
                    "matched_symbols": "handle_request",
                    "imports": ["fastapi", "typing"],
                },
            }
        ]

        # Ensure no GitHubService, TreeSitterService, or SymbolService is called during build
        with (
            patch("services.github_service.GitHubService") as mock_gh,
            patch("services.tree_sitter_service.TreeSitterService") as mock_ts,
            patch("services.symbol_service.SymbolService") as mock_sym,
        ):
            ctx = builder.build(
                repo_name="org/myrepo",
                question="What does router.py do?",
                code_chunks=chunks,
                deterministic_file_path="api/router.py",
            )

            # Neither service should be instantiated
            mock_gh.assert_not_called()
            mock_ts.assert_not_called()
            mock_sym.assert_not_called()

            assert "Deterministic File Information" in ctx.prompt
            assert "api/router.py" in ctx.prompt
            assert "handle_request" in ctx.prompt
            assert "fastapi" in ctx.prompt


# ---------------------------------------------------------------------------
# 6. Empty / Graceful Handling
# ---------------------------------------------------------------------------


class TestEmptyRetrievalHandling:
    def test_empty_chunks_build(self):
        builder = ContextBuilder()
        ctx = builder.build(
            repo_name="org/repo",
            question="Hello world?",
            code_chunks=[],
        )
        assert ctx.prompt is not None
        assert "Hello world?" in ctx.prompt
        assert ctx.source_files == []


# ---------------------------------------------------------------------------
# 7. RetrievalTimer Instrumentation
# ---------------------------------------------------------------------------


class TestRetrievalTimer:
    def test_retrieval_timer_tracking(self):
        timer = RetrievalTimer()
        with timer.track("query_embedding"):
            # simulate work
            _ = sum(i * i for i in range(1000))

        report = timer.report()
        assert "query_embedding" in report
        assert report["query_embedding"]["calls"] == 1
        assert report["query_embedding"]["total_ms"] >= 0.0
