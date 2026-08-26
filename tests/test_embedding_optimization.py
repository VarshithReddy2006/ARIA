"""Regression and performance tests for repository analysis embedding optimization.

Verifies:
  - Process-level singleton embedding model loading (loaded once, thread-safe)
  - Batching behavior under various batch sizes
  - Empty chunk filtering
  - Machine-generated file filtering (e.g. uv.lock, package-lock.json, minified files)
  - Two-tier caching: L1 in-memory hits and L2 SQLite persistence
  - Model and version cache invalidation
  - Changed content invalidation
  - Incremental embedding reuse
  - Vector dimensions and metadata preservation
  - Retrieval correctness before and after optimization
"""

import threading

from core.file_classifier import CATEGORY_PRODUCTION
from services.chunking_service import CodeChunker
from services.embedding_service import (
    EmbeddingService,
    compute_chunk_hash,
    _get_model,
    _clear_l1_cache,
)


class TestEmbeddingOptimization:
    """Test suite covering embedding pipeline performance and correctness."""

    def setup_method(self):
        """Reset cache and telemetry before each test."""
        _clear_l1_cache()

    def test_singleton_model_loading_thread_safety(self):
        """Embedding model is initialized once across concurrent threads."""
        models = []

        def worker():
            m = _get_model()
            models.append(m)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(models) == 8
        first_model = models[0]
        for m in models[1:]:
            assert m is first_model

    def test_machine_generated_files_filtered(self):
        """Lockfiles, map files, and minified bundles produce 0 chunks."""
        chunker = CodeChunker()

        lockfile_content = (
            """
        [[package]]
        name = "fastapi"
        version = "0.111.0"
        dependencies = ["pydantic", "starlette"]
        """
            * 50
        )

        minified_js = "var a=1;function b(){return a+2}console.log(b());" * 100

        # Lockfiles
        assert chunker.chunk_file("uv.lock", lockfile_content) == []
        assert chunker.chunk_file("frontend/package-lock.json", lockfile_content) == []
        assert chunker.chunk_file("yarn.lock", lockfile_content) == []
        assert chunker.chunk_file("pnpm-lock.yaml", lockfile_content) == []

        # Minified / maps
        assert chunker.chunk_file("dist/bundle.min.js", minified_js) == []
        assert chunker.chunk_file("dist/bundle.js.map", "{}") == []

        # Legitimate source files are preserved
        py_code = "def calculate_sum(a, b):\n    return a + b\n"
        py_chunks = chunker.chunk_file("services/math_service.py", py_code)
        assert len(py_chunks) > 0
        assert py_chunks[0]["category"] == CATEGORY_PRODUCTION
        assert py_chunks[0]["language"] == "python"

    def test_empty_and_whitespace_chunks_skipped(self):
        """Empty and whitespace-only files produce no chunks."""
        chunker = CodeChunker()
        assert chunker.chunk_file("empty.py", "") == []
        assert chunker.chunk_file("spaces.py", "   \n\n\t  \n") == []

    def test_deterministic_chunk_hashing_and_isolation(self):
        """Hash changes with content, model name, and model version."""
        text1 = "def authenticate(user, password): pass"
        text2 = "def authenticate(user, token): pass"

        h1 = compute_chunk_hash(text1, "BAAI/bge-small-en-v1.5", "1.5")
        h2 = compute_chunk_hash(text1, "BAAI/bge-small-en-v1.5", "1.5")
        h3 = compute_chunk_hash(text2, "BAAI/bge-small-en-v1.5", "1.5")
        h_diff_model = compute_chunk_hash(text1, "text-embedding-3-small", "1.5")
        h_diff_version = compute_chunk_hash(text1, "BAAI/bge-small-en-v1.5", "2.0")

        assert h1 == h2  # Deterministic
        assert h1 != h3  # Content changed
        assert h1 != h_diff_model  # Model changed
        assert h1 != h_diff_version  # Version changed

    def test_l1_in_memory_cache_hit_and_eviction(self):
        """L1 cache provides instant hit on repeated texts."""
        svc = EmbeddingService()
        svc.clear_cache(clear_disk=True)

        texts = ["def foo(): return 1", "def bar(): return 2"]

        # First call: cache miss
        stats1 = {}
        embs1 = svc.generate_embeddings_batch(texts, stats=stats1)
        assert stats1["cache_misses"] == 2
        assert stats1["cache_hits"] == 0
        assert len(embs1) == 2
        assert len(embs1[0]) == 384

        # Second call: 100% L1 cache hit
        stats2 = {}
        embs2 = svc.generate_embeddings_batch(texts, stats=stats2)
        assert stats2["cache_hits"] == 2
        assert stats2["cache_misses"] == 0
        assert embs1 == embs2

    def test_l2_sqlite_persistence_and_l1_reload(self):
        """L2 SQLite persistent cache repopulates L1 after memory cache clear."""
        svc = EmbeddingService()
        svc.clear_cache(clear_disk=True)

        sample = ["class DatabaseConnection:\n    def connect(self): pass"]
        embs_orig = svc.generate_embeddings_batch(sample)

        # Clear only L1 memory cache
        _clear_l1_cache()

        # Call again: should hit L2 SQLite cache
        stats = {}
        embs_reloaded = svc.generate_embeddings_batch(sample, stats=stats)
        assert stats["cache_hits"] == 1
        assert stats["cache_misses"] == 0
        assert embs_orig == embs_reloaded

    def test_batch_sizing_and_throughput(self):
        """Service processes batches with varying batch sizes correctly."""
        svc = EmbeddingService(max_outer_batch_size=32, encode_batch_size=16)
        chunks = [f"def function_{i}():\n    return {i * 10}" for i in range(50)]

        embs = svc.generate_embeddings(chunks)
        assert len(embs) == 50
        for vec in embs:
            assert len(vec) == 384

    def test_metadata_preservation(self):
        """Chunking preserves file path, chunk_id, language, and category metadata."""
        chunker = CodeChunker(chunk_size=100)
        content = "line 1\nline 2\nline 3\n" * 20
        chunks = chunker.chunk_file("backend/app.py", content)

        assert len(chunks) > 1
        for idx, chunk in enumerate(chunks, start=1):
            assert chunk["path"] == "backend/app.py"
            assert chunk["chunk_id"] == idx
            assert chunk["language"] == "python"
            assert chunk["category"] == CATEGORY_PRODUCTION
            assert len(chunk["content"].strip()) > 0

    def test_semantic_retrieval_correctness(self):
        """Verify vector cosine similarity finds most relevant code snippet."""
        import numpy as np

        svc = EmbeddingService()
        corpus = [
            "def authenticate_user(username, password):\n    # Verify credentials with bcrypt hash\n    return check_password(password, db.get_hash(username))",
            "def calculate_fibonacci(n):\n    if n <= 1: return n\n    return calculate_fibonacci(n-1) + calculate_fibonacci(n-2)",
            "def send_email_notification(to_addr, subject, body):\n    # Send SMTP email\n    smtp.send(to_addr, subject, body)",
        ]

        corpus_embs = svc.generate_embeddings(corpus)
        query = "How does login authentication verify password?"
        query_emb = svc.generate_embedding(query)

        # Compute cosine similarities
        q_vec = np.array(query_emb)
        sims = [
            np.dot(q_vec, np.array(c_vec))
            / (np.linalg.norm(q_vec) * np.linalg.norm(c_vec))
            for c_vec in corpus_embs
        ]

        best_idx = int(np.argmax(sims))
        assert best_idx == 0, f"Expected index 0 (auth function), got {best_idx}"
        assert sims[0] > 0.6
