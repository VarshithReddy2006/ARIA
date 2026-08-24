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
from typing import List, Union, Dict, Any, Optional, Generator, Tuple
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
_inference_lock = threading.Lock()
_model = None
_MODEL_NAME = "BAAI/bge-small-en-v1.5"
DEFAULT_OUTER_BATCH_SIZE = 256
DEFAULT_ENCODE_BATCH_SIZE = 128


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

            os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
            if hasattr(torch, "set_num_threads"):
                num_threads = min(4, os.cpu_count() or 4)
                torch.set_num_threads(num_threads)
            if hasattr(torch, "set_num_interop_threads"):
                torch.set_num_interop_threads(min(2, os.cpu_count() or 2))

            from sentence_transformers import SentenceTransformer  # type: ignore

            logger.info("Loading BGE embedding model '%s' (first call)…", _MODEL_NAME)
            t0 = time.perf_counter()
            _model = SentenceTransformer(_MODEL_NAME)
            logger.info(
                "BGE model loaded successfully. elapsed=%.2fs",
                time.perf_counter() - t0,
            )
        except Exception as exc:
            logger.warning(
                "Failed to load SentenceTransformer model '%s': %s. Falling back to dummy model.",
                _MODEL_NAME,
                exc,
            )

            class _DummyModel:
                def encode(
                    self,
                    texts,
                    batch_size=1,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                ):
                    # Return zero vectors of length 384 (typical BGE dimension)
                    dim = 384
                    return [[0.0] * dim for _ in texts]

            _model = _DummyModel()

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
        max_outer_batch_size: int = DEFAULT_OUTER_BATCH_SIZE,
        encode_batch_size: int = DEFAULT_ENCODE_BATCH_SIZE,
    ) -> None:
        if client is not None:
            logger.debug(
                "EmbeddingService: 'client' parameter is ignored — using local BGE model."
            )
        self.model_name = model_name
        self.max_outer_batch_size = max(1, max_outer_batch_size)
        self.encode_batch_size = max(1, encode_batch_size)

    # ------------------------------------------------------------------
    # Core embedding methods
    # ------------------------------------------------------------------

    def generate_embedding(self, text: str) -> List[float]:
        """Generate a single embedding vector for the given text."""
        res = self.generate_embeddings_batch([text])
        return res[0]

    def generate_embeddings_batch(
        self,
        texts: List[str],
        max_outer_batch_size: Optional[int] = None,
    ) -> List[List[float]]:
        """Generate embeddings for a list of strings in bounded batches using a SQLite cache.

        Args:
            texts: List of input strings.
            max_outer_batch_size: Optional override for outer batch size.

        Returns:
            A list of embedding vectors in the exact original order.
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

        # 2. Process cache misses in bounded outer batches
        if uncached_texts:
            unique_uncached: List[str] = []
            unique_to_idx: Dict[str, int] = {}
            for t in uncached_texts:
                if t not in unique_to_idx:
                    unique_to_idx[t] = len(unique_uncached)
                    unique_uncached.append(t)

            model = _get_model()
            batch_size = self.encode_batch_size
            outer_batch_limit = (
                max(1, max_outer_batch_size)
                if max_outer_batch_size is not None
                else self.max_outer_batch_size
            )

            total_unique = len(unique_uncached)
            total_batches = (total_unique + outer_batch_limit - 1) // outer_batch_limit
            completed_items = 0

            for batch_num, start_idx in enumerate(
                range(0, total_unique, outer_batch_limit), start=1
            ):
                end_idx = min(start_idx + outer_batch_limit, total_unique)
                batch_texts = unique_uncached[start_idx:end_idx]
                batch_count = len(batch_texts)

                t0 = time.perf_counter()
                with _inference_lock:
                    encoded = model.encode(
                        batch_texts,
                        batch_size=batch_size,
                        normalize_embeddings=True,
                        show_progress_bar=False,
                    )
                elapsed = time.perf_counter() - t0
                completed_items += batch_count

                logger.info(
                    "BGE encode progress batch=%d/%d items=%d completed=%d/%d elapsed=%.2fs",
                    batch_num,
                    total_batches,
                    batch_count,
                    completed_items,
                    total_unique,
                    elapsed,
                )

                batch_encoded_list = [
                    vec.tolist() if hasattr(vec, "tolist") else list(vec)
                    for vec in encoded
                ]
                batch_text_to_vec = dict(zip(batch_texts, batch_encoded_list))

                batch_text_set = set(batch_texts)
                records_to_cache: List[Dict[str, Any]] = []

                for idx, orig_idx in enumerate(uncached_indices):
                    pt = uncached_texts[idx]
                    if pt in batch_text_set:
                        embedding_val = batch_text_to_vec[pt]
                        results[orig_idx] = embedding_val
                        records_to_cache.append(
                            {
                                "chunk_hash": hashes[orig_idx],
                                "embedding": embedding_val,
                                "model_name": self.model_name,
                                "model_version": "1.5",
                            }
                        )

                if records_to_cache:
                    _save_embeddings_to_cache_bulk(records_to_cache)

                # Release temporary objects to free memory before next batch
                del encoded
                del batch_encoded_list
                del batch_text_to_vec
                del batch_texts
                del batch_text_set
                del records_to_cache

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

    def stream_generate_embeddings_batches(
        self,
        chunks: List[Union[str, Dict[str, Any], Any]],
        batch_size: Optional[int] = None,
    ) -> Generator[Tuple[List[Any], List[List[float]]], None, None]:
        """Generate embeddings in bounded batches, yielding (batch_chunks, batch_embeddings).

        Yields each batch immediately so callers (like repository indexing) can consume
        and index vectors incrementally without accumulating the entire repository embedding
        matrix in memory.
        """
        if not chunks:
            return

        effective_batch_size = (
            max(1, batch_size) if batch_size is not None else self.max_outer_batch_size
        )
        total_chunks = len(chunks)

        for start_idx in range(0, total_chunks, effective_batch_size):
            end_idx = min(start_idx + effective_batch_size, total_chunks)
            chunk_slice = chunks[start_idx:end_idx]

            # Extract texts for this slice
            texts: List[str] = []
            for c in chunk_slice:
                if isinstance(c, str):
                    texts.append(c)
                elif isinstance(c, dict) and "content" in c:
                    texts.append(c["content"])
                elif hasattr(c, "content"):
                    texts.append(getattr(c, "content"))
                else:
                    texts.append(str(c))

            batch_embs = self.generate_embeddings_batch(
                texts, max_outer_batch_size=effective_batch_size
            )
            yield chunk_slice, batch_embs

            del texts
            del batch_embs
