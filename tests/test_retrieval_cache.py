"""Tests for RetrievalLRUCache and ChromaDB Cache Invalidation Lifecycle.

Verifies:
  1. First query -> cache miss, populates cache
  2. Identical query -> cache hit
  3. Query variance -> cache miss
  4. Repository isolation -> cache miss across repos
  5. Index version isolation -> cache miss when version changes
  6. Re-indexing -> invalidates repository cache entries
  7. Clear database / Delete repo -> invalidates cache
  8. Concurrent queries -> thread-safety under high load
  9. LRU Eviction -> bounded capacity maintained
 10. Immutability -> mutation of returned chunks does not corrupt cache
"""

import concurrent.futures
from services.chat.retrieval_cache import RetrievalLRUCache, retrieval_cache


class TestRetrievalLRUCache:
    def setup_method(self):
        retrieval_cache.invalidate_all()
        retrieval_cache.reset_metrics()

    def test_miss_then_hit(self):
        cache = RetrievalLRUCache(max_entries=10)
        key = cache.build_key("org/repo", "v1", "how does auth work?", 15, 5)

        # 1. First query -> Miss
        assert cache.get(key) is None
        metrics = cache.get_metrics()
        assert metrics["misses"] == 1
        assert metrics["hits"] == 0

        # Store result
        mock_chunks = [
            {
                "id": "chunk_1",
                "content": "auth code",
                "metadata": {"file_path": "auth.py"},
            }
        ]
        mock_ret_metrics = {"total_ms": 120.5, "initial_retrieved": 1}
        cache.put(key, "org/repo", mock_chunks, mock_ret_metrics)

        # 2. Second query -> Hit
        hit_result = cache.get(key)
        assert hit_result is not None
        chunks, ret_metrics = hit_result
        assert len(chunks) == 1
        assert chunks[0]["content"] == "auth code"
        metrics = cache.get_metrics()
        assert metrics["hits"] == 1
        assert metrics["hit_rate_pct"] == 50.0

    def test_query_and_repo_isolation(self):
        cache = RetrievalLRUCache(max_entries=10)
        k1 = cache.build_key("org/repo1", "v1", "query a", 15, 5)
        k2 = cache.build_key("org/repo1", "v1", "query b", 15, 5)
        k3 = cache.build_key("org/repo2", "v1", "query a", 15, 5)

        cache.put(k1, "org/repo1", [{"id": "1", "content": "a"}], {})

        assert cache.get(k1) is not None
        assert cache.get(k2) is None
        assert cache.get(k3) is None

    def test_index_version_isolation(self):
        cache = RetrievalLRUCache(max_entries=10)
        k_v1 = cache.build_key("org/repo", "v1", "same query", 15, 5)
        k_v2 = cache.build_key("org/repo", "v2", "same query", 15, 5)

        cache.put(k_v1, "org/repo", [{"id": "1", "content": "old version"}], {})

        assert cache.get(k_v1) is not None
        assert cache.get(k_v2) is None

    def test_explicit_repo_invalidation(self):
        cache = RetrievalLRUCache(max_entries=10)
        k1 = cache.build_key("org/repo1", "v1", "query 1", 15, 5)
        k2 = cache.build_key("org/repo1", "v1", "query 2", 15, 5)
        k3 = cache.build_key("org/repo2", "v1", "query 1", 15, 5)

        cache.put(k1, "org/repo1", [{"id": "1"}], {})
        cache.put(k2, "org/repo1", [{"id": "2"}], {})
        cache.put(k3, "org/repo2", [{"id": "3"}], {})

        assert cache.get_metrics()["current_size"] == 3

        # Invalidate repo1
        invalidated = cache.invalidate_repo("org/repo1")
        assert invalidated == 2
        assert cache.get(k1) is None
        assert cache.get(k2) is None
        assert cache.get(k3) is not None
        assert cache.get_metrics()["current_size"] == 1

    def test_lru_eviction(self):
        cache = RetrievalLRUCache(max_entries=3)

        k1 = cache.build_key("r", "v", "q1")
        k2 = cache.build_key("r", "v", "q2")
        k3 = cache.build_key("r", "v", "q3")
        k4 = cache.build_key("r", "v", "q4")

        cache.put(k1, "r", [{"id": "1"}], {})
        cache.put(k2, "r", [{"id": "2"}], {})
        cache.put(k3, "r", [{"id": "3"}], {})

        # Access k1 to make k2 the least recently used
        cache.get(k1)

        # Insert k4 -> should evict k2
        cache.put(k4, "r", [{"id": "4"}], {})

        assert cache.get(k1) is not None
        assert cache.get(k2) is None
        assert cache.get(k3) is not None
        assert cache.get(k4) is not None
        assert cache.get_metrics()["evictions"] == 1
        assert cache.get_metrics()["current_size"] == 3

    def test_immutability_deep_copy(self):
        cache = RetrievalLRUCache(max_entries=10)
        k = cache.build_key("r", "v", "q")
        original_chunk = {"id": "1", "metadata": {"tags": ["secure"]}}
        cache.put(k, "r", [original_chunk], {"metric": 100})

        # Fetch and mutate
        res, _ = cache.get(k)
        res[0]["metadata"]["tags"].append("mutated")
        res[0]["metadata"]["extra"] = "injected"

        # Fetch again and verify pristine
        res2, _ = cache.get(k)
        assert res2[0]["metadata"]["tags"] == ["secure"]
        assert "extra" not in res2[0]["metadata"]

    def test_concurrent_access_thread_safety(self):
        cache = RetrievalLRUCache(max_entries=50)

        def worker(idx: int):
            q = f"query_{idx % 10}"
            key = cache.build_key("repo", "v1", q)
            res = cache.get(key)
            if res is None:
                cache.put(key, "repo", [{"id": str(idx), "content": f"data_{idx}"}], {})
            return True

        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
            futures = [executor.submit(worker, i) for i in range(200)]
            results = [f.result() for f in futures]

        assert all(results)
        metrics = cache.get_metrics()
        assert metrics["current_size"] <= 50
        assert metrics["hits"] + metrics["misses"] >= 200

    def test_chroma_reindex_and_delete_invalidation(self, tmp_path):
        import uuid
        from memory.chroma_store import ChromaStore

        store = ChromaStore(persist_directory=str(tmp_path / "chroma_test"))
        repo_name = f"test_owner/repo_{uuid.uuid4().hex[:6]}"

        chunks = [{"content": "def authenticate(): pass", "path": "auth.py"}]
        embeddings = [[0.1] * 384]

        # 1. Index repository
        store.index_repository(repo_name, chunks, embeddings)
        v1 = store._active_version(repo_name)
        assert v1 is not None

        # Populate cache
        k1 = retrieval_cache.build_key(repo_name, v1, "how does authenticate work?")
        retrieval_cache.put(
            k1, repo_name, [{"id": "c1", "content": "auth"}], {"search_ms": 50}
        )
        assert retrieval_cache.get(k1) is not None

        # 2. Re-index repository (generates new version and invalidates repo cache)
        new_chunks = [{"content": "def authenticate_v2(): pass", "path": "auth.py"}]
        store.index_repository(repo_name, new_chunks, embeddings)
        v2 = store._active_version(repo_name)
        assert v2 != v1

        # Old cache entry must be invalidated
        assert retrieval_cache.get(k1) is None
        # Old version key should miss even if looked up directly
        k_old = retrieval_cache.build_key(repo_name, v1, "how does authenticate work?")
        assert retrieval_cache.get(k_old) is None

        # 3. Delete files invalidation
        k2 = retrieval_cache.build_key(repo_name, v2, "test query")
        retrieval_cache.put(k2, repo_name, [{"id": "c2"}], {})
        assert retrieval_cache.get(k2) is not None
        store.delete_files(repo_name, ["auth.py"])
        assert retrieval_cache.get(k2) is None

        # 4. Clear database invalidation
        k3 = retrieval_cache.build_key(repo_name, v2, "test query 3")
        retrieval_cache.put(k3, repo_name, [{"id": "c3"}], {})
        store.clear_database()
        assert retrieval_cache.get(k3) is None
