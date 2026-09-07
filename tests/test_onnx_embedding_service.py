"""Tests for ONNX and PyTorch Embedding Backends, shape validation, and cache safety."""

import concurrent.futures
import numpy as np

from services.embedding_service import (
    EmbeddingService,
    ONNXEmbeddingBackend,
    PyTorchEmbeddingBackend,
    _get_backend,
    _clear_l1_cache,
)


def test_pytorch_backend_init():
    """Verify PyTorch backend initializes and outputs [N, 384] normalized vectors."""
    backend = PyTorchEmbeddingBackend()
    texts = ["def foo(): return 42", "class Bar: pass"]
    embs = backend.encode(texts, normalize_embeddings=True)

    assert isinstance(embs, np.ndarray)
    assert embs.shape == (2, 384)
    assert np.all(np.isfinite(embs))
    # Check L2 normalization
    norms = np.linalg.norm(embs, axis=1)
    np.testing.assert_allclose(norms, [1.0, 1.0], atol=1e-5)


def test_onnx_fp32_backend_init():
    """Verify ONNX FP32 backend initializes and outputs [N, 384] normalized vectors."""
    backend = ONNXEmbeddingBackend(quantization="fp32")
    texts = ["def foo(): return 42", "class Bar: pass"]
    embs = backend.encode(texts, normalize_embeddings=True)

    assert isinstance(embs, np.ndarray)
    assert embs.shape == (2, 384)
    assert np.all(np.isfinite(embs))
    norms = np.linalg.norm(embs, axis=1)
    np.testing.assert_allclose(norms, [1.0, 1.0], atol=1e-5)


def test_onnx_int8_backend_init():
    """Verify ONNX INT8 backend initializes and outputs [N, 384] normalized vectors."""
    backend = ONNXEmbeddingBackend(quantization="int8")
    texts = ["def foo(): return 42", "class Bar: pass"]
    embs = backend.encode(texts, normalize_embeddings=True)

    assert isinstance(embs, np.ndarray)
    assert embs.shape == (2, 384)
    assert np.all(np.isfinite(embs))
    norms = np.linalg.norm(embs, axis=1)
    np.testing.assert_allclose(norms, [1.0, 1.0], atol=1e-5)


def test_onnx_int8_cosine_fidelity():
    """Verify ONNX INT8 vectors have high cosine similarity (>0.96) with PyTorch vectors."""
    pt_backend = PyTorchEmbeddingBackend()
    onnx_backend = ONNXEmbeddingBackend(quantization="int8")

    sample_texts = [
        "public static final int BUFFER_SIZE = 4096;",
        "def compute_hash(data: bytes) -> str: return hashlib.sha256(data).hexdigest()",
        "import React, { useState } from 'react';",
        "SELECT id, name, created_at FROM users WHERE status = 'active';",
    ]

    pt_embs = pt_backend.encode(sample_texts, normalize_embeddings=True)
    onnx_embs = onnx_backend.encode(sample_texts, normalize_embeddings=True)

    for i in range(len(sample_texts)):
        cos_sim = float(np.dot(pt_embs[i], onnx_embs[i]))
        assert cos_sim >= 0.96, f"Cosine similarity too low for item {i}: {cos_sim:.4f}"


def test_embedding_service_with_onnx():
    """Verify EmbeddingService works end-to-end with ONNX backend."""
    _clear_l1_cache()
    svc = EmbeddingService()
    svc.clear_cache(clear_disk=True)

    chunks = [
        {"content": "def add(a, b): return a + b"},
        {"content": "def sub(a, b): return a - b"},
    ]

    stats = {}
    embs = svc.generate_embeddings(chunks, stats=stats)

    assert len(embs) == 2
    assert len(embs[0]) == 384
    assert len(embs[1]) == 384
    assert stats["cache_misses"] == 2
    assert stats["cache_hits"] == 0

    # Warm cache test
    stats_warm = {}
    embs_warm = svc.generate_embeddings(chunks, stats=stats_warm)
    assert len(embs_warm) == 2
    assert stats_warm["cache_hits"] == 2
    assert stats_warm["cache_misses"] == 0
    assert np.allclose(embs[0], embs_warm[0], atol=1e-6)


def test_backend_fallback_on_invalid():
    """Verify _get_backend gracefully falls back to PyTorch or safe backend on error."""
    # When an invalid backend is requested, it should safely handle without crashing
    backend = _get_backend(backend_override="invalid_backend_name")
    assert backend is not None
    embs = backend.encode(["test text"])
    assert embs.shape == (1, 384)


def test_concurrent_embedding_service_thread_safety():
    """Verify that multiple concurrent threads can safely call generate_embeddings_batch."""
    _clear_l1_cache()
    svc = EmbeddingService()

    texts = [f"Unique text chunk for concurrency test {i}" for i in range(20)]

    def _worker(slice_texts):
        return svc.generate_embeddings_batch(slice_texts)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(_worker, texts[i : i + 5]) for i in range(0, len(texts), 5)
        ]
        results = [f.result() for f in futures]

    for res in results:
        assert len(res) == 5
        for vec in res:
            assert len(vec) == 384
            assert np.all(np.isfinite(vec))


def test_cache_keys_backend_and_quantization_aware():
    """Verify compute_chunk_hash differentiates between backends and quantizations."""
    from services.embedding_service import (
        compute_chunk_hash,
        compute_chunk_hashes_bulk,
    )

    text = "def hello_world(): return 42"
    h_pt = compute_chunk_hash(
        text, "BAAI/bge-small-en-v1.5", "v1.5", backend="pytorch", quantization="none"
    )
    h_onnx_fp32 = compute_chunk_hash(
        text, "BAAI/bge-small-en-v1.5", "v1.5", backend="onnx", quantization="none"
    )
    h_onnx_int8 = compute_chunk_hash(
        text, "BAAI/bge-small-en-v1.5", "v1.5", backend="onnx", quantization="int8"
    )

    # All hashes must be mutually distinct to prevent cache collision
    assert len({h_pt, h_onnx_fp32, h_onnx_int8}) == 3

    # Bulk hashing matches single hashing
    bulk_hashes = compute_chunk_hashes_bulk(
        [text],
        "BAAI/bge-small-en-v1.5",
        "v1.5",
        backend="onnx",
        quantization="int8",
    )
    assert bulk_hashes[0] == h_onnx_int8
