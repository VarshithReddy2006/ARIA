"""Embedding Service — local BGE embeddings via sentence-transformers.

Replaces Gemini text-embedding-004 with BAAI/bge-small-en-v1.5 running
entirely locally. No API calls, no quotas, no API key required.

Public interface is identical to the previous Gemini-backed version so all
callers (RetrievalService, IssueMapper, ChromaStore, api.py) continue to work
without modification.
"""

import logging
import threading
import time
import hashlib
import json
from typing import List, Union, Dict, Any, Optional
from storage.migrations import get_db_connection

logger = logging.getLogger(__name__)


# SQLite embedding cache helpers
def _get_cached_embedding(chunk_hash: str, model_name: str) -> Optional[List[float]]:
    res = _get_cached_embeddings_bulk([chunk_hash], model_name)
    return res.get(chunk_hash)


def _get_cached_embeddings_bulk(
    chunk_hashes: List[str], model_name: str
) -> Dict[str, List[float]]:
    if not chunk_hashes:
        return {}
    results: Dict[str, List[float]] = {}
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        batch_size = 900
        for i in range(0, len(chunk_hashes), batch_size):
            batch = chunk_hashes[i : i + batch_size]
            placeholders = ",".join("?" for _ in batch)
            cursor.execute(
                f"SELECT chunk_hash, embedding FROM embedding_cache WHERE model_name = ? AND chunk_hash IN ({placeholders})",
                [model_name] + batch,
            )
            for row in cursor.fetchall():
                try:
                    results[row[0]] = json.loads(row[1])
                except Exception:
                    pass
    except Exception as e:
        logger.warning("Failed bulk lookup of embeddings in SQLite cache: %s", e)
    finally:
        conn.close()
    return results


def _save_embeddings_to_cache_bulk(records: List[Dict[str, Any]]) -> None:
    if not records:
        return
    conn = get_db_connection()
    try:
        with conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO embedding_cache (chunk_hash, embedding, model_name, model_version, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                [
                    (
                        r["chunk_hash"],
                        json.dumps(r["embedding"]),
                        r["model_name"],
                        r["model_version"],
                    )
                    for r in records
                ],
            )
    except Exception as e:
        logger.warning("Failed to save embeddings in SQLite cache: %s", e)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Model singleton — loaded once and reused across all calls
# ---------------------------------------------------------------------------
_model_lock = threading.Lock()
_model = None
_MODEL_NAME = "BAAI/bge-small-en-v1.5"


def _get_model():
    """Return the cached SentenceTransformer model, loading it on first call."""
    global _model
    if _model is not None:
        return _model

    with _model_lock:
        if _model is not None:  # double-checked locking
            return _model

        try:
            import os
            import torch

            if hasattr(torch, "set_num_threads"):
                num_threads = min(8, os.cpu_count() or 4)
                torch.set_num_threads(num_threads)

            from sentence_transformers import SentenceTransformer  # type: ignore

            logger.info("Loading BGE embedding model '%s' (first call)…", _MODEL_NAME)
            t0 = time.perf_counter()
            _model = SentenceTransformer(_MODEL_NAME)
            logger.info(
                "BGE model loaded successfully. elapsed=%.2fs",
                time.perf_counter() - t0,
            )
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is not installed. "
                "Run: pip install sentence-transformers"
            ) from exc

    return _model


# ---------------------------------------------------------------------------
# Compatibility shim — call_with_retry was imported by other modules from here
# ---------------------------------------------------------------------------


def call_with_retry(
    func,
    *args,
    max_retries: int = 5,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    **kwargs,
):
    """Thin compatibility shim — local inference never needs retry, but this
    function is imported by agents/evaluator.py and agents/issue_mapper.py so
    it must remain importable.  For local models it simply calls the function
    directly.
    """
    return func(*args, **kwargs)


# ---------------------------------------------------------------------------
# EmbeddingService
# ---------------------------------------------------------------------------


class EmbeddingService:
    """Generates dense vector embeddings using a local BGE model.

    Drop-in replacement for the previous Gemini-backed EmbeddingService.
    Constructor accepts the same optional `client` and `model_name` kwargs so
    existing call-sites that pass `client=...` do not break.
    """

    def __init__(
        self,
        client: Any = None,  # accepted but ignored (Gemini client)
        model_name: str = _MODEL_NAME,
    ) -> None:
        if client is not None:
            logger.debug(
                "EmbeddingService: 'client' parameter is ignored — using local BGE model."
            )
        self.model_name = model_name

    # ------------------------------------------------------------------
    # Core embedding methods
    # ------------------------------------------------------------------

    def generate_embedding(self, text: str) -> List[float]:
        """Generate a single embedding vector for the given text."""
        res = self.generate_embeddings_batch([text])
        return res[0]

    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of strings in one efficient batch using a SQLite cache.

        Args:
            texts: List of input strings.

        Returns:
            A list of embedding vectors.
        """
        if not texts:
            return []

        results: List[Optional[List[float]]] = [None] * len(texts)
        prefixed_texts = [f"Represent this sentence: {t}" for t in texts]
        hashes = [hashlib.md5(pt.encode("utf-8")).hexdigest() for pt in prefixed_texts]

        # 1. Query SQLite cache in bulk
        cached_map = _get_cached_embeddings_bulk(hashes, self.model_name)

        uncached_texts: List[str] = []
        uncached_indices: List[int] = []

        for idx, chunk_hash in enumerate(hashes):
            if chunk_hash in cached_map:
                results[idx] = cached_map[chunk_hash]
            else:
                uncached_texts.append(prefixed_texts[idx])
                uncached_indices.append(idx)

        # 2. Process cache misses in batch
        if uncached_texts:
            unique_uncached: List[str] = []
            unique_to_idx: Dict[str, int] = {}
            for t in uncached_texts:
                if t not in unique_to_idx:
                    unique_to_idx[t] = len(unique_uncached)
                    unique_uncached.append(t)

            model = _get_model()
            batch_size = 128
            t0 = time.perf_counter()
            encoded = model.encode(
                unique_uncached,
                batch_size=batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            elapsed = time.perf_counter() - t0
            logger.info(
                "BGE encode unique_uncached=%d total_uncached=%d batch_size=%d elapsed=%.2fs",
                len(unique_uncached),
                len(uncached_texts),
                batch_size,
                elapsed,
            )

            unique_embeddings = [vec.tolist() for vec in encoded]
            records_to_cache = []

            for idx, orig_idx in enumerate(uncached_indices):
                pt = uncached_texts[idx]
                chunk_hash = hashes[orig_idx]
                embedding_val = unique_embeddings[unique_to_idx[pt]]
                results[orig_idx] = embedding_val

                records_to_cache.append(
                    {
                        "chunk_hash": chunk_hash,
                        "embedding": embedding_val,
                        "model_name": self.model_name,
                        "model_version": "1.5",
                    }
                )

            _save_embeddings_to_cache_bulk(records_to_cache)

        return results  # type: ignore

    def generate_embeddings(
        self, chunks: List[Union[str, Dict[str, Any], Any]]
    ) -> List[List[float]]:
        """Generate embeddings for a mixed list of chunks, dicts, or strings.

        Accepts the same input formats as the old Gemini-backed version:
        - Plain strings
        - Dicts with a "content" key
        - Objects with a .content attribute

        Args:
            chunks: List of chunk structures or text strings.

        Returns:
            A list of embedding vectors.
        """
        texts: List[str] = []
        for c in chunks:
            if isinstance(c, str):
                texts.append(c)
            elif isinstance(c, dict) and "content" in c:
                texts.append(c["content"])
            elif hasattr(c, "content"):
                texts.append(getattr(c, "content"))
            else:
                texts.append(str(c))

        return self.generate_embeddings_batch(texts)
