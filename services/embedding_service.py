"""Embedding Service — local BGE embeddings via SentenceTransformers / ONNX Runtime INT8 with two-tier caching.

Replaces Gemini text-embedding-004 with BAAI/bge-small-en-v1.5 running
entirely locally. No API calls, no quotas, no API key required.

Features:
  - Pluggable inference backends: ONNX Runtime (INT8/FP32) + PyTorch fallback
  - Process-level thread-safe singleton model initialization
  - Two-tier caching: L1 in-memory LRU cache + L2 SQLite persistent cache (WAL mode)
  - Deterministic SHA-256 content-addressed chunk hashing isolated by model/version
  - Optimized cold-path: bulk hash → bulk L1 → bulk L2 → batch encode → bulk write
  - Configurable outer/encode batch sizing
  - Structured performance and telemetry tracking
"""

from abc import ABC, abstractmethod
import hashlib
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple, Union

import numpy as np

from core.config import settings
from storage.migrations import get_db_connection

logger = logging.getLogger(__name__)

# Model configuration defaults
_MODEL_NAME = "BAAI/bge-small-en-v1.5"
_MODEL_VERSION = "1.5"
DEFAULT_OUTER_BATCH_SIZE = getattr(settings, "embedding_batch_size", 64)
DEFAULT_ENCODE_BATCH_SIZE = getattr(settings, "embedding_encode_batch_size", 64)
DEFAULT_CACHE_SIZE = getattr(settings, "embedding_cache_size", 50000)

# Bulk operation limits
CACHE_LOOKUP_BATCH_SIZE = 900  # SQLite parameter limit safety
CACHE_WRITE_BATCH_SIZE = 1000  # Bounded write transactions


# ---------------------------------------------------------------------------
# Deterministic SHA-256 Chunk Hashing (Backend/Model/Quantization/Version Aware)
# ---------------------------------------------------------------------------
def compute_chunk_hash(
    text: str,
    model_name: str = _MODEL_NAME,
    model_version: str = _MODEL_VERSION,
    backend: Optional[str] = None,
    quantization: Optional[str] = None,
) -> str:
    """Compute deterministic SHA-256 hash incorporating content, model, backend, and quantization metadata."""
    backend_val = (
        (
            backend
            if backend is not None
            else getattr(settings, "embedding_backend", "onnx")
        )
        .lower()
        .strip()
    )
    quant_val = (
        (
            quantization
            if quantization is not None
            else (
                getattr(settings, "embedding_onnx_quantization", "int8")
                if backend_val == "onnx"
                else "none"
            )
        )
        .lower()
        .strip()
    )
    normalized = text.strip()
    key = f"{model_name}:{model_version}:{backend_val}:{quant_val}:{normalized}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def compute_chunk_hashes_bulk(
    texts: List[str],
    model_name: str = _MODEL_NAME,
    model_version: str = _MODEL_VERSION,
    backend: Optional[str] = None,
    quantization: Optional[str] = None,
) -> List[str]:
    """Compute deterministic SHA-256 hashes for all texts in one pass incorporating backend and quantization."""
    backend_val = (
        (
            backend
            if backend is not None
            else getattr(settings, "embedding_backend", "onnx")
        )
        .lower()
        .strip()
    )
    quant_val = (
        (
            quantization
            if quantization is not None
            else (
                getattr(settings, "embedding_onnx_quantization", "int8")
                if backend_val == "onnx"
                else "none"
            )
        )
        .lower()
        .strip()
    )
    prefix = f"{model_name}:{model_version}:{backend_val}:{quant_val}:"
    results = []
    for t in texts:
        normalized = t.strip()
        key = f"{prefix}{normalized}"
        results.append(hashlib.sha256(key.encode("utf-8")).hexdigest())
    return results


# ---------------------------------------------------------------------------
# L1 In-Memory LRU Cache
# ---------------------------------------------------------------------------
_l1_lock = threading.Lock()
_l1_cache: OrderedDict[str, List[float]] = OrderedDict()
_l1_max_size: int = DEFAULT_CACHE_SIZE


def _get_l1_cached(chunk_hash: str) -> Optional[List[float]]:
    """Retrieve an embedding from L1 in-memory LRU cache."""
    with _l1_lock:
        if chunk_hash in _l1_cache:
            _l1_cache.move_to_end(chunk_hash)
            return _l1_cache[chunk_hash]
    return None


def _get_l1_cached_bulk(chunk_hashes: List[str]) -> Dict[str, List[float]]:
    """Retrieve multiple embeddings from L1 cache in a single lock acquisition."""
    if not chunk_hashes:
        return {}
    results: Dict[str, List[float]] = {}
    with _l1_lock:
        for h in chunk_hashes:
            if h in _l1_cache:
                _l1_cache.move_to_end(h)
                results[h] = _l1_cache[h]
    return results


def _put_l1_cached_bulk(records: Dict[str, List[float]]) -> None:
    """Insert embeddings into L1 in-memory LRU cache with capacity eviction."""
    if not records:
        return
    with _l1_lock:
        for chunk_hash, embedding in records.items():
            if chunk_hash in _l1_cache:
                _l1_cache.move_to_end(chunk_hash)
            else:
                if len(_l1_cache) >= _l1_max_size:
                    _l1_cache.popitem(last=False)
                _l1_cache[chunk_hash] = embedding


def _clear_l1_cache() -> None:
    """Clear in-memory L1 cache."""
    with _l1_lock:
        _l1_cache.clear()


# ---------------------------------------------------------------------------
# L2 SQLite Persistent Cache Helpers
# ---------------------------------------------------------------------------
def _init_sqlite_cache_table() -> None:
    """Ensure SQLite cache table and index exist with WAL mode and concurrency safety."""
    try:
        conn = get_db_connection()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS embedding_cache (
                    chunk_hash TEXT PRIMARY KEY,
                    embedding TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_embedding_cache_model_hash
                ON embedding_cache(model_name, chunk_hash);
                """
            )
            conn.execute("COMMIT;")
        except Exception as exc:
            try:
                conn.execute("ROLLBACK;")
            except Exception:
                pass
            logger.debug("SQLite cache table init notice: %s", exc)
        finally:
            conn.close()
    except Exception as exc:
        logger.debug("SQLite cache connection notice: %s", exc)


def _get_cached_embedding(
    chunk_hash: str, model_name: str = _MODEL_NAME
) -> Optional[List[float]]:
    res = _get_cached_embeddings_bulk([chunk_hash], model_name)
    return res.get(chunk_hash)


def _get_cached_embeddings_bulk(
    chunk_hashes: List[str], model_name: str = _MODEL_NAME
) -> Dict[str, List[float]]:
    """Retrieve embeddings from L2 SQLite database in chunks.

    Uses a single connection and processes hashes in batches of CACHE_LOOKUP_BATCH_SIZE
    to respect SQLite parameter limits.
    """
    if not chunk_hashes:
        return {}
    results: Dict[str, List[float]] = {}
    conn = get_db_connection()
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        cursor = conn.cursor()
        for i in range(0, len(chunk_hashes), CACHE_LOOKUP_BATCH_SIZE):
            batch = chunk_hashes[i : i + CACHE_LOOKUP_BATCH_SIZE]
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
    """Save newly generated embeddings to L2 SQLite cache in bounded transactions.

    Processes records in batches of CACHE_WRITE_BATCH_SIZE for memory safety.
    Uses a single connection with WAL mode and BEGIN IMMEDIATE for concurrency safety.
    """
    if not records:
        return
    try:
        conn = get_db_connection()
        try:
            for i in range(0, len(records), CACHE_WRITE_BATCH_SIZE):
                batch = records[i : i + CACHE_WRITE_BATCH_SIZE]
                try:
                    conn.execute("BEGIN IMMEDIATE;")
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
                            for r in batch
                        ],
                    )
                    conn.execute("COMMIT;")
                except Exception as batch_exc:
                    try:
                        conn.execute("ROLLBACK;")
                    except Exception:
                        pass
                    logger.warning(
                        "Failed to save batch of embeddings to SQLite cache: %s",
                        batch_exc,
                    )
        finally:
            conn.close()
    except Exception as e:
        logger.warning(
            "Failed to open connection to save embeddings in SQLite cache: %s", e
        )


# ---------------------------------------------------------------------------
# Embedding Backends
# ---------------------------------------------------------------------------
class BaseEmbeddingBackend(ABC):
    """Abstract base class for embedding inference backends."""

    @abstractmethod
    def encode(
        self,
        texts: List[str],
        batch_size: int = 64,
        normalize_embeddings: bool = True,
        show_progress_bar: bool = False,
    ) -> np.ndarray:
        """Encode texts into embeddings with shape [N, 384]."""
        pass


class PyTorchEmbeddingBackend(BaseEmbeddingBackend):
    """PyTorch SentenceTransformer backend."""

    def __init__(self, model_name: str = _MODEL_NAME) -> None:
        self.model_name = model_name
        import torch

        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        if hasattr(torch, "set_num_threads"):
            try:
                num_threads = min(os.cpu_count() or 4, 8)
                torch.set_num_threads(num_threads)
            except Exception:
                pass
        if hasattr(torch, "set_num_interop_threads"):
            try:
                torch.set_num_interop_threads(min(4, os.cpu_count() or 2))
            except Exception:
                pass

        from sentence_transformers import SentenceTransformer  # type: ignore

        logger.info("Loading PyTorch SentenceTransformer model '%s'…", model_name)
        self.model = SentenceTransformer(model_name)

    def encode(
        self,
        texts: List[str],
        batch_size: int = 64,
        normalize_embeddings: bool = True,
        show_progress_bar: bool = False,
    ) -> np.ndarray:
        return self.model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=normalize_embeddings,
            show_progress_bar=show_progress_bar,
        )


class ONNXEmbeddingBackend(BaseEmbeddingBackend):
    """ONNX Runtime embedding backend with INT8/FP32 inference."""

    def __init__(
        self,
        model_name: str = _MODEL_NAME,
        quantization: str = "int8",
        threads: Optional[int] = None,
    ) -> None:
        self.model_name = model_name
        self.quantization = quantization.lower().strip()
        self.threads = (
            threads
            if threads is not None
            else getattr(settings, "embedding_onnx_threads", None)
            or min(os.cpu_count() or 4, 8)
        )

        import onnxruntime as ort
        from transformers import AutoTokenizer

        logger.info(
            "Initializing ONNXEmbeddingBackend (model='%s', quantization='%s', threads=%d)…",
            model_name,
            self.quantization,
            self.threads,
        )

        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        model_path = self._ensure_onnx_model()

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = self.threads
        opts.inter_op_num_threads = min(4, os.cpu_count() or 2)
        opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        self.session = ort.InferenceSession(
            model_path,
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )
        logger.info(
            "ONNX session initialized successfully from '%s' (%s mode).",
            model_path,
            self.quantization,
        )

    def _get_model_cache_dir(self) -> str:
        cache_base = os.environ.get(
            "ARIA_MODEL_CACHE_DIR",
            os.path.expanduser("~/.cache/aria/models"),
        )
        safe_name = self.model_name.replace("/", "_")
        target_dir = os.path.join(cache_base, safe_name)
        os.makedirs(target_dir, exist_ok=True)
        return target_dir

    def _ensure_onnx_model(self) -> str:
        """Ensure ONNX FP32 and INT8 models exist on disk, exporting if necessary."""
        cache_dir = self._get_model_cache_dir()
        fp32_path = os.path.join(cache_dir, "model.onnx")
        int8_path = os.path.join(cache_dir, "model_int8.onnx")

        # 1. Check if requested model already exists
        if self.quantization == "int8" and os.path.exists(int8_path):
            return int8_path
        if self.quantization == "fp32" and os.path.exists(fp32_path):
            return fp32_path

        # 2. Export FP32 if needed
        if not os.path.exists(fp32_path):
            logger.info("Exporting '%s' to ONNX FP32 format…", self.model_name)
            import torch
            from transformers import AutoModel

            class _BertWrapper(torch.nn.Module):
                def __init__(self, model):
                    super().__init__()
                    self.model = model

                def forward(self, input_ids, attention_mask, token_type_ids):
                    out = self.model(
                        input_ids=input_ids,
                        attention_mask=attention_mask,
                        token_type_ids=token_type_ids,
                        return_dict=True,
                    )
                    return out.last_hidden_state

            pt_model = AutoModel.from_pretrained(self.model_name)
            pt_model.eval()
            wrapper = _BertWrapper(pt_model)
            wrapper.eval()

            dummy_text = ["Represent this sentence: def sample(): return 1"]
            inputs = self.tokenizer(
                dummy_text,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            dummy_input = (
                inputs["input_ids"],
                inputs["attention_mask"],
                inputs["token_type_ids"],
            )

            input_names = ["input_ids", "attention_mask", "token_type_ids"]
            dynamic_axes = {
                "input_ids": {0: "batch_size", 1: "sequence_length"},
                "attention_mask": {0: "batch_size", 1: "sequence_length"},
                "token_type_ids": {0: "batch_size", 1: "sequence_length"},
                "last_hidden_state": {0: "batch_size", 1: "sequence_length"},
            }

            temp_fp32 = fp32_path + ".tmp"
            with torch.no_grad():
                torch.onnx.export(
                    wrapper,
                    dummy_input,
                    temp_fp32,
                    input_names=input_names,
                    output_names=["last_hidden_state"],
                    dynamic_axes=dynamic_axes,
                    opset_version=14,
                    do_constant_folding=True,
                    dynamo=False,
                )
            if os.path.exists(fp32_path):
                try:
                    os.remove(fp32_path)
                except Exception:
                    pass
            os.replace(temp_fp32, fp32_path)
            logger.info(
                "ONNX FP32 export complete: %s (%.2f MB)",
                fp32_path,
                os.path.getsize(fp32_path) / (1024 * 1024),
            )

        # 3. Quantize to INT8 if requested
        if self.quantization == "int8":
            if not os.path.exists(int8_path):
                logger.info("Quantizing ONNX FP32 model to INT8 (MatMul/Gemm)…")
                from onnxruntime.quantization import QuantType, quantize_dynamic

                temp_int8 = int8_path + ".tmp"
                quantize_dynamic(
                    model_input=fp32_path,
                    model_output=temp_int8,
                    weight_type=QuantType.QInt8,
                    op_types_to_quantize=["MatMul", "Gemm"],
                    per_channel=True,
                )
                if os.path.exists(int8_path):
                    try:
                        os.remove(int8_path)
                    except Exception:
                        pass
                os.replace(temp_int8, int8_path)
                logger.info(
                    "ONNX INT8 quantization complete: %s (%.2f MB)",
                    int8_path,
                    os.path.getsize(int8_path) / (1024 * 1024),
                )
            return int8_path

        return fp32_path

    def encode(
        self,
        texts: List[str],
        batch_size: int = 64,
        normalize_embeddings: bool = True,
        show_progress_bar: bool = False,
    ) -> np.ndarray:
        if not texts:
            return np.empty((0, 384), dtype=np.float32)

        all_embs: List[np.ndarray] = []
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            toks = self.tokenizer(
                batch_texts,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="np",
            )
            feed = {
                "input_ids": toks["input_ids"].astype(np.int64),
                "attention_mask": toks["attention_mask"].astype(np.int64),
                "token_type_ids": toks["token_type_ids"].astype(np.int64),
            }
            last_hidden_state = self.session.run(None, feed)[0]

            # CLS token pooling (BGE uses [CLS] token embedding at index 0)
            cls_token = last_hidden_state[:, 0]

            if normalize_embeddings:
                norms = np.linalg.norm(cls_token, axis=1, keepdims=True)
                norms = np.where(norms == 0, 1e-12, norms)
                cls_token = cls_token / norms

            all_embs.append(cls_token.astype(np.float32))

        return np.vstack(all_embs)


# ---------------------------------------------------------------------------
# Backend Singleton & Factory
# ---------------------------------------------------------------------------
_model_lock = threading.Lock()
_inference_lock = threading.Lock()
_backend_instance: Optional[BaseEmbeddingBackend] = None
_model_load_time_ms: float = 0.0


def _get_backend(
    backend_override: Optional[str] = None,
    quantization_override: Optional[str] = None,
) -> BaseEmbeddingBackend:
    """Return the cached embedding backend, initializing or failing over safely."""
    global _backend_instance, _model_load_time_ms
    if _backend_instance is not None and backend_override is None:
        return _backend_instance

    with _model_lock:
        if _backend_instance is not None and backend_override is None:
            return _backend_instance

        t0 = time.perf_counter()
        target_backend = (
            (
                backend_override
                if backend_override is not None
                else getattr(settings, "embedding_backend", "onnx")
            )
            .lower()
            .strip()
        )
        target_quant = (
            quantization_override
            if quantization_override is not None
            else getattr(settings, "embedding_onnx_quantization", "int8")
        )

        backend: Optional[BaseEmbeddingBackend] = None

        if target_backend == "onnx":
            try:
                backend = ONNXEmbeddingBackend(
                    model_name=_MODEL_NAME,
                    quantization=target_quant,
                )
            except Exception as onnx_err:
                logger.warning(
                    "ONNXEmbeddingBackend initialization failed (%s). Falling back to PyTorch: %s",
                    onnx_err,
                    onnx_err,
                    exc_info=True,
                )
                try:
                    backend = PyTorchEmbeddingBackend(model_name=_MODEL_NAME)
                except Exception as pt_err:
                    logger.error(
                        "Both ONNX and PyTorch backend initializations failed: %s",
                        pt_err,
                    )

        elif target_backend == "pytorch":
            try:
                backend = PyTorchEmbeddingBackend(model_name=_MODEL_NAME)
            except Exception as pt_err:
                logger.error("PyTorch backend initialization failed: %s", pt_err)

        if backend is None:
            # Fallback dummy backend
            class _DummyBackend(BaseEmbeddingBackend):
                def encode(
                    self,
                    texts,
                    batch_size=1,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                ):
                    return np.zeros((len(texts), 384), dtype=np.float32)

            backend = _DummyBackend()

        if backend_override is None:
            _backend_instance = backend
            _model_load_time_ms = (time.perf_counter() - t0) * 1000.0

        return backend


def _get_model():
    """Backward compatibility shim returning the active embedding backend."""
    return _get_backend()


# ---------------------------------------------------------------------------
# Compatibility Shim
# ---------------------------------------------------------------------------
def call_with_retry(
    func,
    *args,
    max_retries: int = 5,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    **kwargs,
):
    """Thin compatibility shim for callers expecting retry behavior."""
    return func(*args, **kwargs)


# ---------------------------------------------------------------------------
# Embedding Telemetry Tracker
# ---------------------------------------------------------------------------
@dataclass
class EmbeddingTelemetry:
    chunks_total: int = 0
    chunks_skipped: int = 0
    chunks_embedded: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    batch_count: int = 0
    embedding_time_ms: float = 0.0
    vector_write_time_ms: float = 0.0
    throughput_chunks_per_sec: float = 0.0
    model_load_time_ms: float = 0.0
    # Granular timing (cold-path optimization)
    hash_time_ms: float = 0.0
    l1_lookup_time_ms: float = 0.0
    l2_lookup_time_ms: float = 0.0
    l2_write_time_ms: float = 0.0
    total_embed_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunks_total": self.chunks_total,
            "chunks_skipped": self.chunks_skipped,
            "chunks_embedded": self.chunks_embedded,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "batch_count": self.batch_count,
            "embedding_time_ms": round(self.embedding_time_ms, 2),
            "vector_write_time_ms": round(self.vector_write_time_ms, 2),
            "throughput_chunks_per_sec": round(self.throughput_chunks_per_sec, 2),
            "model_load_time_ms": round(self.model_load_time_ms, 2),
            "hash_time_ms": round(self.hash_time_ms, 2),
            "l1_lookup_time_ms": round(self.l1_lookup_time_ms, 2),
            "l2_lookup_time_ms": round(self.l2_lookup_time_ms, 2),
            "l2_write_time_ms": round(self.l2_write_time_ms, 2),
            "total_embed_time_ms": round(self.total_embed_time_ms, 2),
        }


# ---------------------------------------------------------------------------
# EmbeddingService
# ---------------------------------------------------------------------------
class EmbeddingService:
    """Generates dense vector embeddings using local BGE model with two-tier caching."""

    def __init__(
        self,
        client: Any = None,
        model_name: str = _MODEL_NAME,
        max_outer_batch_size: Optional[int] = None,
        encode_batch_size: Optional[int] = None,
        backend_name: Optional[str] = None,
        quantization: Optional[str] = None,
    ) -> None:
        if client is not None:
            logger.debug(
                "EmbeddingService: 'client' parameter ignored — using local BGE model."
            )
        self.model_name = model_name
        self.model_version = _MODEL_VERSION
        self.backend_name = (
            (
                getattr(settings, "embedding_backend", "onnx")
                if backend_name is None
                else backend_name
            )
            .lower()
            .strip()
        )
        self.quantization = (
            (
                getattr(settings, "embedding_onnx_quantization", "int8")
                if (quantization is None and self.backend_name == "onnx")
                else (quantization or "none")
            )
            .lower()
            .strip()
        )
        self.max_outer_batch_size = max(
            1,
            max_outer_batch_size
            if max_outer_batch_size is not None
            else getattr(settings, "embedding_batch_size", DEFAULT_OUTER_BATCH_SIZE),
        )
        self.encode_batch_size = max(
            1,
            encode_batch_size
            if encode_batch_size is not None
            else getattr(
                settings, "embedding_encode_batch_size", DEFAULT_ENCODE_BATCH_SIZE
            ),
        )
        self.telemetry = EmbeddingTelemetry()
        self._telemetry_lock = threading.Lock()
        _init_sqlite_cache_table()

    def get_telemetry(self) -> Dict[str, Any]:
        """Return a snapshot of embedding performance telemetry."""
        with self._telemetry_lock:
            self.telemetry.model_load_time_ms = _model_load_time_ms
            return self.telemetry.to_dict()

    def reset_telemetry(self) -> None:
        """Reset internal telemetry counters."""
        with self._telemetry_lock:
            self.telemetry = EmbeddingTelemetry()

    def clear_cache(self, clear_disk: bool = False) -> None:
        """Clear L1 in-memory cache and optionally L2 disk cache."""
        _clear_l1_cache()
        if clear_disk:
            try:
                conn = get_db_connection()
                try:
                    conn.execute("BEGIN IMMEDIATE;")
                    conn.execute(
                        "DELETE FROM embedding_cache WHERE model_name = ?",
                        [self.model_name],
                    )
                    conn.execute("COMMIT;")
                except Exception as e:
                    try:
                        conn.execute("ROLLBACK;")
                    except Exception:
                        pass
                    logger.warning("Failed to clear SQLite cache: %s", e)
                finally:
                    conn.close()
            except Exception as e:
                logger.warning("Failed to connect to SQLite to clear cache: %s", e)

    def generate_embedding(self, text: str) -> List[float]:
        """Generate a single embedding vector for the given text."""
        res = self.generate_embeddings_batch([text])
        return res[0]

    def generate_embeddings_batch(
        self,
        texts: List[str],
        max_outer_batch_size: Optional[int] = None,
        stats: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> List[List[float]]:
        """Generate embeddings for a list of strings with optimized bulk pipeline.

        Optimized cold-path flow:
          1. Bulk hash ALL texts in one pass
          2. Bulk L1 lookup (single lock acquisition)
          3. Bulk L2 lookup (single SQLite query)
          4. Deduplicate cache misses
          5. Batch model.encode() on misses only
          6. Deferred bulk L2 write (single transaction)
          7. Bulk L1 update

        Args:
            texts: List of input strings.
            max_outer_batch_size: Optional override for outer batch size.
            stats: Optional dictionary to receive live telemetry stats.
            progress_callback: Optional callback receiving per-batch progress metadata.

        Returns:
            A list of embedding vectors in the exact original order.
        """
        if not texts:
            return []

        t_start = time.perf_counter()
        total_texts = len(texts)
        results: List[Optional[List[float]]] = [None] * total_texts

        # ── 1. Bulk hash ALL texts ──────────────────────────────────────────
        t_hash_start = time.perf_counter()
        prefixed_texts = [f"Represent this sentence: {t}" for t in texts]
        hashes = compute_chunk_hashes_bulk(
            prefixed_texts,
            self.model_name,
            self.model_version,
            backend=self.backend_name,
            quantization=self.quantization,
        )
        t_hash = time.perf_counter() - t_hash_start

        # ── 2. Bulk L1 lookup (single lock acquisition) ────────────────────
        t_l1_start = time.perf_counter()
        l1_map = _get_l1_cached_bulk(hashes)
        t_l1 = time.perf_counter() - t_l1_start

        l1_hits = 0
        l1_miss_indices: List[int] = []
        for idx, h in enumerate(hashes):
            if h in l1_map:
                results[idx] = l1_map[h]
                l1_hits += 1
            else:
                l1_miss_indices.append(idx)

        # ── 3. Bulk L2 SQLite lookup (single query for all L1 misses) ──────
        t_l2_start = time.perf_counter()
        l2_hits = 0
        uncached_indices: List[int] = []
        if l1_miss_indices:
            miss_hashes = [hashes[i] for i in l1_miss_indices]
            l2_cached_map = _get_cached_embeddings_bulk(miss_hashes, self.model_name)

            for idx in l1_miss_indices:
                h = hashes[idx]
                if h in l2_cached_map:
                    results[idx] = l2_cached_map[h]
                    l2_hits += 1
                else:
                    uncached_indices.append(idx)

            # Promote L2 hits to L1 for future instant reuse
            if l2_cached_map:
                _put_l1_cached_bulk(l2_cached_map)
        t_l2 = time.perf_counter() - t_l2_start

        cache_hit_count = l1_hits + l2_hits
        cache_miss_count = len(uncached_indices)

        # If everything was cached, notify progress_callback of 100% completion immediately
        if not uncached_indices and progress_callback is not None:
            try:
                progress_callback(
                    {
                        "batch": 1,
                        "total_batches": 1,
                        "batch_items": 0,
                        "completed_chunks": total_texts,
                        "total_chunks": total_texts,
                        "progress_pct": 100.0,
                        "cache_hits": cache_hit_count,
                        "cache_misses": 0,
                        "elapsed_batch_seconds": 0.0,
                    }
                )
            except Exception as cb_err:
                logger.debug(
                    "Embedding progress callback error (cache hit): %s", cb_err
                )

        # ── 4. Process cache misses: deduplicate → batch encode ────────────
        t_inference_start = time.perf_counter()
        batches_processed = 0
        all_new_embeddings: Dict[str, List[float]] = {}  # hash → embedding

        if uncached_indices:
            uncached_texts = [prefixed_texts[i] for i in uncached_indices]
            uncached_hashes = [hashes[i] for i in uncached_indices]

            # Deduplicate: only encode unique texts
            unique_texts: List[str] = []
            unique_hashes: List[str] = []
            seen_hashes: set = set()
            for i, h in enumerate(uncached_hashes):
                if h not in seen_hashes:
                    seen_hashes.add(h)
                    unique_texts.append(uncached_texts[i])
                    unique_hashes.append(h)

            model = _get_model()
            encode_batch_size = self.encode_batch_size
            total_unique = len(unique_texts)

            outer_limit = (
                max(1, max_outer_batch_size)
                if max_outer_batch_size is not None
                else self.max_outer_batch_size
            )

            batches_processed = (total_unique + outer_limit - 1) // outer_limit

            for batch_num, start_idx in enumerate(
                range(0, total_unique, outer_limit), start=1
            ):
                end_idx = min(start_idx + outer_limit, total_unique)
                batch_texts = unique_texts[start_idx:end_idx]
                batch_hashes = unique_hashes[start_idx:end_idx]

                t_b0 = time.perf_counter()
                with _inference_lock:
                    encoded = model.encode(
                        batch_texts,
                        batch_size=encode_batch_size,
                        normalize_embeddings=True,
                        show_progress_bar=False,
                    )
                elapsed_batch = time.perf_counter() - t_b0

                logger.info(
                    "BGE encode progress batch=%d/%d items=%d completed=%d/%d elapsed=%.2fs",
                    batch_num,
                    batches_processed,
                    len(batch_texts),
                    end_idx,
                    total_unique,
                    elapsed_batch,
                )

                # Convert to lists and store
                for i, vec in enumerate(encoded):
                    vec_list = vec.tolist() if hasattr(vec, "tolist") else list(vec)
                    all_new_embeddings[batch_hashes[i]] = vec_list

                if progress_callback is not None:
                    completed_chunks = (
                        min(
                            total_texts,
                            cache_hit_count
                            + int((end_idx / total_unique) * cache_miss_count),
                        )
                        if total_unique > 0
                        else total_texts
                    )
                    pct = round((completed_chunks / max(1, total_texts)) * 100.0, 1)
                    try:
                        progress_callback(
                            {
                                "batch": batch_num,
                                "total_batches": batches_processed,
                                "batch_items": len(batch_texts),
                                "completed_chunks": completed_chunks,
                                "total_chunks": total_texts,
                                "progress_pct": pct,
                                "cache_hits": cache_hit_count,
                                "cache_misses": cache_miss_count,
                                "elapsed_batch_seconds": elapsed_batch,
                            }
                        )
                    except Exception as cb_err:
                        logger.debug("Embedding progress callback error: %s", cb_err)

            # Map results back to original indices
            for idx in uncached_indices:
                h = hashes[idx]
                if h in all_new_embeddings:
                    results[idx] = all_new_embeddings[h]

        t_inference = time.perf_counter() - t_inference_start

        # ── 5. Deferred bulk L2 write (single transaction) ─────────────────
        t_l2_write_start = time.perf_counter()
        if all_new_embeddings:
            l2_records = [
                {
                    "chunk_hash": h,
                    "embedding": vec,
                    "model_name": self.model_name,
                    "model_version": self.model_version,
                }
                for h, vec in all_new_embeddings.items()
            ]
            _save_embeddings_to_cache_bulk(l2_records)
        t_l2_write = time.perf_counter() - t_l2_write_start

        # ── 6. Bulk L1 update with new embeddings ──────────────────────────
        if all_new_embeddings:
            _put_l1_cached_bulk(all_new_embeddings)

        elapsed_s = time.perf_counter() - t_start
        elapsed_ms = elapsed_s * 1000.0

        # ── 7. Update telemetry ────────────────────────────────────────────
        with self._telemetry_lock:
            self.telemetry.chunks_total += total_texts
            self.telemetry.chunks_embedded += cache_miss_count
            self.telemetry.cache_hits += cache_hit_count
            self.telemetry.cache_misses += cache_miss_count
            self.telemetry.batch_count += batches_processed
            self.telemetry.embedding_time_ms += t_inference * 1000.0
            self.telemetry.hash_time_ms += t_hash * 1000.0
            self.telemetry.l1_lookup_time_ms += t_l1 * 1000.0
            self.telemetry.l2_lookup_time_ms += t_l2 * 1000.0
            self.telemetry.l2_write_time_ms += t_l2_write * 1000.0
            self.telemetry.total_embed_time_ms += elapsed_ms
            if self.telemetry.total_embed_time_ms > 0:
                self.telemetry.throughput_chunks_per_sec = (
                    self.telemetry.chunks_total
                    / (self.telemetry.total_embed_time_ms / 1000.0)
                )

        if stats is not None:
            stats["cache_hits"] = cache_hit_count
            stats["cache_misses"] = cache_miss_count
            stats["chunks_processed"] = total_texts
            stats["chunks_total"] = total_texts
            stats["chunks_embedded"] = cache_miss_count
            stats["embedding_time_ms"] = round(t_inference * 1000.0, 2)
            stats["total_embed_time_ms"] = round(elapsed_ms, 2)
            stats["elapsed_ms"] = round(elapsed_ms, 2)
            stats["throughput_chunks_per_sec"] = round(
                total_texts / max(0.001, elapsed_s), 1
            )
            stats["throughput"] = round(total_texts / max(0.001, elapsed_s), 1)
            stats["batch_count"] = batches_processed
            stats["batch_size"] = self.encode_batch_size

        return results  # type: ignore

    def generate_embeddings(
        self,
        chunks: List[Union[str, Dict[str, Any], Any]],
        stats: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> List[List[float]]:
        """Generate embeddings for chunks, dictionaries, or raw strings."""
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

        return self.generate_embeddings_batch(
            texts, stats=stats, progress_callback=progress_callback
        )

    def stream_generate_embeddings_batches(
        self,
        chunks: List[Union[str, Dict[str, Any], Any]],
        batch_size: Optional[int] = None,
    ) -> Generator[Tuple[List[Any], List[List[float]]], None, None]:
        """Generate embeddings in bounded batches, yielding (batch_chunks, batch_embeddings)."""
        if not chunks:
            return

        effective_batch_size = (
            max(1, batch_size) if batch_size is not None else self.max_outer_batch_size
        )
        total_chunks = len(chunks)

        for start_idx in range(0, total_chunks, effective_batch_size):
            end_idx = min(start_idx + effective_batch_size, total_chunks)
            chunk_slice = chunks[start_idx:end_idx]

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
