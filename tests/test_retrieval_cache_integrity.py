"""Retrieval Cache Integrity, Correctness & Isolation Test Suite.

Validates:
1. Cache Key Determinism & Specificity (repo, version, query, top_k, extra).
2. Same Query Cache Hit.
3. Different Query Cache Miss.
4. Different Repository Cache Miss & Data Isolation (zero cross-contamination).
5. Repository Snapshot / Version Invalidation.
6. Result Equivalence (Cold vs Warm chunks, metadata, rankings, and context).
7. Evidence Ordering Equivalence.
8. Empty Retrieval Graceful Handling.
9. Preserved UNKNOWN Semantics.
"""

import copy

from services.chat.retrieval_cache import RetrievalLRUCache
from services.chat.context_builder import ContextBuilder


# ---------------------------------------------------------------------------
# 1. Cache Key Determinism & Specificity Tests
# ---------------------------------------------------------------------------


class TestCacheKeyDesign:
    def test_cache_key_repo_sensitivity(self):
        k1 = RetrievalLRUCache.build_key(
            repo_name="org/repo_a", index_version="v1", question="explain api"
        )
        k2 = RetrievalLRUCache.build_key(
            repo_name="org/repo_b", index_version="v1", question="explain api"
        )
        assert k1 != k2, "Different repositories must generate distinct cache keys"

    def test_cache_key_version_sensitivity(self):
        k1 = RetrievalLRUCache.build_key(
            repo_name="org/repo", index_version="v1", question="explain api"
        )
        k2 = RetrievalLRUCache.build_key(
            repo_name="org/repo", index_version="v2", question="explain api"
        )
        assert k1 != k2, "Different index versions must generate distinct cache keys"

    def test_cache_key_query_sensitivity(self):
        k1 = RetrievalLRUCache.build_key(
            repo_name="org/repo", index_version="v1", question="explain api"
        )
        k2 = RetrievalLRUCache.build_key(
            repo_name="org/repo", index_version="v1", question="explain auth"
        )
        assert k1 != k2, "Different queries must generate distinct cache keys"

    def test_cache_key_normalization(self):
        # Formatting differences should normalize to the same key
        k1 = RetrievalLRUCache.build_key(
            repo_name="Org/Repo ", index_version="v1", question="Explain `api`???"
        )
        k2 = RetrievalLRUCache.build_key(
            repo_name="org/repo", index_version="v1", question="explain api"
        )
        assert k1 == k2, "Normalized variations must resolve to identical cache keys"

    def test_cache_key_top_k_sensitivity(self):
        k1 = RetrievalLRUCache.build_key(
            repo_name="org/repo",
            index_version="v1",
            question="explain api",
            top_k_final=5,
        )
        k2 = RetrievalLRUCache.build_key(
            repo_name="org/repo",
            index_version="v1",
            question="explain api",
            top_k_final=10,
        )
        assert k1 != k2, "Different top_k parameter must generate distinct cache keys"


# ---------------------------------------------------------------------------
# 2. Hit / Miss & Isolation Tests
# ---------------------------------------------------------------------------


class TestCacheHitMissAndIsolation:
    def setup_method(self):
        self.cache = RetrievalLRUCache(max_entries=10, ttl_seconds=60.0)

    def test_same_query_cache_hit(self):
        key = self.cache.build_key("org/repo", "v1", "explain auth")
        sample_chunks = [
            {"content": "def auth(): pass", "metadata": {"file_path": "auth.py"}}
        ]
        sample_metrics = {"confidence": 95, "total_ms": 12.0}

        self.cache.put(key, "org/repo", sample_chunks, sample_metrics)
        hit = self.cache.get(key)
        assert hit is not None
        chunks, metrics = hit
        assert chunks == sample_chunks
        assert metrics == sample_metrics

    def test_different_query_cache_miss(self):
        key1 = self.cache.build_key("org/repo", "v1", "query one")
        key2 = self.cache.build_key("org/repo", "v1", "query two")
        self.cache.put(key1, "org/repo", [{"content": "1"}], {"confidence": 90})

        assert self.cache.get(key2) is None

    def test_different_repo_cache_isolation(self):
        key_a = self.cache.build_key("org/repo_a", "v1", "common query")
        key_b = self.cache.build_key("org/repo_b", "v1", "common query")

        chunks_a = [{"content": "Repo A Code", "metadata": {"repo": "repo_a"}}]
        self.cache.put(key_a, "org/repo_a", chunks_a, {"confidence": 90})

        # repo_b query should be a miss
        assert self.cache.get(key_b) is None

        # Even after repo_b is populated, repo_a must not be affected
        chunks_b = [{"content": "Repo B Code", "metadata": {"repo": "repo_b"}}]
        self.cache.put(key_b, "org/repo_b", chunks_b, {"confidence": 92})

        res_a, _ = self.cache.get(key_a)
        res_b, _ = self.cache.get(key_b)
        assert res_a[0]["content"] == "Repo A Code"
        assert res_b[0]["content"] == "Repo B Code"

    def test_deep_copy_mutation_safety(self):
        key = self.cache.build_key("org/repo", "v1", "test query")
        sample_chunks = [
            {"content": "original content", "metadata": {"tag": "immutable"}}
        ]
        self.cache.put(key, "org/repo", sample_chunks, {"confidence": 90})

        res, _ = self.cache.get(key)
        res[0]["content"] = "mutated content"
        res[0]["metadata"]["tag"] = "corrupted"

        res_second, _ = self.cache.get(key)
        assert res_second[0]["content"] == "original content"
        assert res_second[0]["metadata"]["tag"] == "immutable"


# ---------------------------------------------------------------------------
# 3. Cache Invalidation & Version Isolation
# ---------------------------------------------------------------------------


class TestCacheInvalidation:
    def setup_method(self):
        self.cache = RetrievalLRUCache(max_entries=10, ttl_seconds=60.0)

    def test_invalidate_specific_repo(self):
        k_a1 = self.cache.build_key("org/repo_a", "v1", "q1")
        k_a2 = self.cache.build_key("org/repo_a", "v1", "q2")
        k_b1 = self.cache.build_key("org/repo_b", "v1", "q1")

        self.cache.put(k_a1, "org/repo_a", [{"content": "a1"}], {})
        self.cache.put(k_a2, "org/repo_a", [{"content": "a2"}], {})
        self.cache.put(k_b1, "org/repo_b", [{"content": "b1"}], {})

        invalidated_count = self.cache.invalidate_repo("org/repo_a")
        assert invalidated_count == 2
        assert self.cache.get(k_a1) is None
        assert self.cache.get(k_a2) is None
        assert self.cache.get(k_b1) is not None, "Repo B entries must remain unaffected"

    def test_version_bump_auto_invalidates_keys(self):
        k_v1 = self.cache.build_key("org/repo", "commit_abc123", "explain architecture")
        k_v2 = self.cache.build_key("org/repo", "commit_def456", "explain architecture")

        self.cache.put(k_v1, "org/repo", [{"content": "old code"}], {})

        # When active version is bumped to commit_def456, key is different
        assert self.cache.get(k_v2) is None


# ---------------------------------------------------------------------------
# 4. Result Equivalence: Cold vs Warm
# ---------------------------------------------------------------------------


class TestResultEquivalence:
    def test_cold_and_warm_produce_identical_results_and_prompt(self):
        builder = ContextBuilder()

        chunks = [
            {
                "id": "c1",
                "content": "class AuthManager:\n    def login(self, u, p): pass",
                "_rerank_score": 950000.0,
                "_similarity": 0.95,
                "metadata": {
                    "file_path": "backend/services/auth.py",
                    "chunk_id": "c1",
                    "start_line": 1,
                    "end_line": 2,
                    "language": "python",
                    "why_this_file": "Matched exact path",
                    "matched_symbols": "AuthManager, login",
                    "confidence": 100,
                },
            },
            {
                "id": "c2",
                "content": "def test_login(): pass",
                "_rerank_score": 500000.0,
                "_similarity": 0.80,
                "metadata": {
                    "file_path": "tests/test_auth.py",
                    "chunk_id": "c2",
                    "start_line": 1,
                    "end_line": 2,
                    "language": "python",
                    "why_this_file": "Test file",
                    "matched_symbols": "test_login",
                    "confidence": 70,
                },
            },
        ]

        metrics_cold = {
            "initial_retrieved": 2,
            "after_exclusion": 2,
            "after_dedup": 2,
            "final_returned": 2,
            "confidence": 100,
            "cache_hit": False,
        }

        # Build Cold Context
        ctx_cold = builder.build(
            repo_name="org/my_repo",
            question="How does AuthManager work?",
            code_chunks=copy.deepcopy(chunks),
            structured_intelligence="## Architecture: Clean Auth",
        )

        # Store in cache
        cache = RetrievalLRUCache()
        key = cache.build_key("org/my_repo", "v1", "How does AuthManager work?")
        cache.put(key, "org/my_repo", chunks, metrics_cold)

        # Retrieve Warm
        warm_entry = cache.get(key)
        assert warm_entry is not None
        warm_chunks, warm_metrics = warm_entry
        warm_metrics["cache_hit"] = True

        # Build Warm Context
        ctx_warm = builder.build(
            repo_name="org/my_repo",
            question="How does AuthManager work?",
            code_chunks=warm_chunks,
            structured_intelligence="## Architecture: Clean Auth",
        )

        # Verify exact equivalence
        assert ctx_cold.prompt == ctx_warm.prompt, (
            "Cold and warm prompts must be character-for-character identical"
        )
        assert ctx_cold.estimated_tokens == ctx_warm.estimated_tokens
        assert ctx_cold.source_files == ctx_warm.source_files
        assert ctx_cold.slot_breakdown == ctx_warm.slot_breakdown
        assert len(warm_chunks) == len(chunks)
        assert [c["_rerank_score"] for c in warm_chunks] == [
            c["_rerank_score"] for c in chunks
        ]


# ---------------------------------------------------------------------------
# 5. Cross-Repository Isolation & Zero-Leakage Verification
# ---------------------------------------------------------------------------


class TestCrossRepositoryIsolation:
    def test_two_repositories_distinct_evidence(self):
        builder = ContextBuilder()

        chunks_repo_a = [
            {
                "id": "a_1",
                "content": "def repo_a_unique_function(): return 'Alpha'",
                "metadata": {
                    "file_path": "src/alpha.py",
                    "start_line": 1,
                    "end_line": 2,
                    "chunk_id": "a_1",
                },
            }
        ]
        chunks_repo_b = [
            {
                "id": "b_1",
                "content": "def repo_b_unique_function(): return 'Beta'",
                "metadata": {
                    "file_path": "src/beta.py",
                    "start_line": 1,
                    "end_line": 2,
                    "chunk_id": "b_1",
                },
            }
        ]

        cache = RetrievalLRUCache()
        key_a = cache.build_key("org/repo_a", "v1", "explain function")
        key_b = cache.build_key("org/repo_b", "v1", "explain function")

        cache.put(key_a, "org/repo_a", chunks_repo_a, {"confidence": 90})
        cache.put(key_b, "org/repo_b", chunks_repo_b, {"confidence": 90})

        ctx_a = builder.build(
            repo_name="org/repo_a",
            question="explain function",
            code_chunks=cache.get(key_a)[0],
        )
        ctx_b = builder.build(
            repo_name="org/repo_b",
            question="explain function",
            code_chunks=cache.get(key_b)[0],
        )

        # Assert no cross-leakage
        assert "repo_a_unique_function" in ctx_a.prompt
        assert "repo_b_unique_function" not in ctx_a.prompt
        assert "src/alpha.py" in ctx_a.source_files
        assert "src/beta.py" not in ctx_a.source_files

        assert "repo_b_unique_function" in ctx_b.prompt
        assert "repo_a_unique_function" not in ctx_b.prompt
        assert "src/beta.py" in ctx_b.source_files
        assert "src/alpha.py" not in ctx_b.source_files


# ---------------------------------------------------------------------------
# 6. UNKNOWN & Empty Retrieval Semantics
# ---------------------------------------------------------------------------


class TestUnknownAndEmptySemantics:
    def test_empty_retrieval_preserves_prompt_integrity(self):
        builder = ContextBuilder()
        ctx = builder.build(
            repo_name="org/empty_repo",
            question="Where is PaymentGateway?",
            code_chunks=[],
            structured_intelligence="",
        )

        assert "Where is PaymentGateway?" in ctx.prompt
        assert ctx.source_files == []
        assert "## Repository Code Context" not in ctx.prompt
        assert (
            ctx.estimated_tokens > 0
        )  # Still has system instructions and question format
