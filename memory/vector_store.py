"""Unified Vector Store Production Abstraction Layer (Phase 3).

Provides a clean VectorStore interface and ProductionVectorStore adapter
implementing Primary (Qdrant) / Rollback Fallback (ChromaDB) routing,
dual-write ingestion, version-isolated indexing, and comprehensive observability.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from core.config import Settings
from memory.chroma_store import ChromaStore
from memory.qdrant_store import QdrantStore

logger = logging.getLogger(__name__)


@runtime_checkable
class VectorStore(Protocol):
    """Protocol defining the standard vector store contract for ARIA."""

    def search_repository(
        self, repo_name: str, query_embedding: List[float], limit: int = 5
    ) -> List[Dict[str, Any]]: ...

    def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 5,
        where_filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]: ...

    def search_similar_code(
        self,
        query_embedding: List[float],
        limit: int = 5,
        where_filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]: ...

    def index_repository(
        self,
        repo_name: str,
        chunks: List[Dict[str, Any]],
        embeddings: List[List[float]],
    ) -> None: ...

    def stage_repository_batch(
        self,
        repo_name: str,
        version: str,
        chunks: List[Dict[str, Any]],
        embeddings: List[List[float]],
        start_chunk_id: int = 0,
    ) -> int: ...

    def publish_repository_version(
        self,
        repo_name: str,
        version: str,
    ) -> None: ...

    def rollback_staged_version(
        self,
        repo_name: str,
        version: str,
    ) -> None: ...

    def get_repository_file_paths(self, repo_name: str) -> List[str]: ...

    def get_file_chunks(self, repo_name: str, file_path: str) -> Dict[str, Any]: ...

    def delete_files(self, repo_name: str, file_paths: List[str]) -> None: ...

    def delete_repository(self, repo_name: str) -> None: ...

    def clear_database(self) -> None: ...

    def _active_version(self, repo_name: str) -> Optional[str]: ...


class VectorStoreTelemetry:
    """Thread-safe telemetry and metrics tracker for vector store operations."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.qdrant_requests: int = 0
        self.qdrant_errors: int = 0
        self.qdrant_timeouts: int = 0
        self.qdrant_retries: int = 0
        self.chroma_requests: int = 0
        self.chroma_fallback_count: int = 0
        self.dual_write_success_count: int = 0
        self.dual_write_error_count: int = 0
        self.shadow_comparisons: int = 0
        self.shadow_mismatches: int = 0
        self.total_search_latencies_ms: List[float] = []

    def record_qdrant_request(self, latency_ms: float, success: bool = True) -> None:
        with self._lock:
            self.qdrant_requests += 1
            if not success:
                self.qdrant_errors += 1
            if len(self.total_search_latencies_ms) < 1000:
                self.total_search_latencies_ms.append(latency_ms)

    def record_fallback(self) -> None:
        with self._lock:
            self.chroma_fallback_count += 1
            self.chroma_requests += 1

    def record_dual_write(self, success: bool = True) -> None:
        with self._lock:
            if success:
                self.dual_write_success_count += 1
            else:
                self.dual_write_error_count += 1

    def record_shadow(self, match: bool) -> None:
        with self._lock:
            self.shadow_comparisons += 1
            if not match:
                self.shadow_mismatches += 1

    def get_metrics(self) -> Dict[str, Any]:
        with self._lock:
            avg_lat = (
                sum(self.total_search_latencies_ms)
                / max(1, len(self.total_search_latencies_ms))
                if self.total_search_latencies_ms
                else 0.0
            )
            return {
                "qdrant_requests": self.qdrant_requests,
                "qdrant_errors": self.qdrant_errors,
                "qdrant_timeouts": self.qdrant_timeouts,
                "qdrant_retries": self.qdrant_retries,
                "chroma_requests": self.chroma_requests,
                "chroma_fallback_count": self.chroma_fallback_count,
                "dual_write_success_count": self.dual_write_success_count,
                "dual_write_error_count": self.dual_write_error_count,
                "shadow_comparisons": self.shadow_comparisons,
                "shadow_mismatches": self.shadow_mismatches,
                "avg_qdrant_search_latency_ms": round(avg_lat, 3),
            }


class ProductionVectorStore:
    """Production Vector Store adapter with Dual-Write, Primary Qdrant, and Chroma Fallback."""

    def __init__(
        self,
        primary_store: Optional[VectorStore] = None,
        fallback_store: Optional[VectorStore] = None,
        settings: Optional[Settings] = None,
        enable_fallback: bool = True,
        enable_shadow: bool = False,
    ) -> None:
        self.settings = settings or Settings()
        self.enable_fallback = enable_fallback
        self.enable_shadow = enable_shadow
        self.telemetry = VectorStoreTelemetry()

        # Initialize Primary Store (Qdrant)
        if primary_store is not None:
            self.primary = primary_store
        else:
            try:
                self.primary = QdrantStore(
                    url=self.settings.qdrant_url,
                    grpc_port=self.settings.qdrant_grpc_port,
                    prefer_grpc=self.settings.qdrant_prefer_grpc,
                    api_key=self.settings.qdrant_api_key,
                    timeout=self.settings.qdrant_timeout,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to initialize primary QdrantStore: %s. Using local ChromaStore fallback.",
                    exc,
                )
                self.primary = None

        # Initialize Fallback Store (ChromaDB)
        if fallback_store is not None:
            self.fallback = fallback_store
        else:
            self.fallback = ChromaStore(persist_directory=self.settings.chroma_db_path)

        self._active_backend = "qdrant" if self.primary is not None else "chroma"

    @property
    def active_backend(self) -> str:
        return self._active_backend

    def _execute_with_fallback(
        self,
        method_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Executes operation on primary vector store with observable Chroma fallback."""
        if self.primary is not None and self._active_backend == "qdrant":
            t0 = time.perf_counter()
            try:
                method = getattr(self.primary, method_name)
                res = method(*args, **kwargs)
                lat_ms = (time.perf_counter() - t0) * 1000.0
                self.telemetry.record_qdrant_request(lat_ms, success=True)

                # Shadow execution if enabled
                if self.enable_shadow and self.fallback is not None:
                    try:
                        fallback_method = getattr(self.fallback, method_name)
                        fallback_res = fallback_method(*args, **kwargs)
                        match = self._compare_results(res, fallback_res)
                        self.telemetry.record_shadow(match)
                    except Exception as s_exc:
                        logger.debug("Shadow validation execution error: %s", s_exc)

                return res
            except Exception as exc:
                lat_ms = (time.perf_counter() - t0) * 1000.0
                self.telemetry.record_qdrant_request(lat_ms, success=False)
                logger.warning(
                    "Primary QdrantStore.%s failed (%s). Fallback enabled=%s",
                    method_name,
                    exc,
                    self.enable_fallback,
                )
                if not self.enable_fallback:
                    raise

        # Execute on fallback
        if self.fallback is not None:
            self.telemetry.record_fallback()
            fallback_method = getattr(self.fallback, method_name)
            return fallback_method(*args, **kwargs)

        raise RuntimeError(
            f"No available vector store to execute {method_name} (Primary and Fallback unavailable)."
        )

    @staticmethod
    def _compare_results(res_primary: Any, res_fallback: Any) -> bool:
        """Compare primary vs fallback retrieval results for shadow validation."""
        if not isinstance(res_primary, list) or not isinstance(res_fallback, list):
            return res_primary == res_fallback
        if len(res_primary) != len(res_fallback):
            return False
        # Compare IDs and file_paths of top results
        for p, f in zip(res_primary, res_fallback):
            if isinstance(p, dict) and isinstance(f, dict):
                p_meta = p.get("metadata", {})
                f_meta = f.get("metadata", {})
                if p_meta.get("file_path") != f_meta.get("file_path"):
                    return False
        return True

    def _active_version(self, repo_name: str) -> Optional[str]:
        return self._execute_with_fallback("_active_version", repo_name)

    def search_repository(
        self, repo_name: str, query_embedding: List[float], limit: int = 5
    ) -> List[Dict[str, Any]]:
        return self._execute_with_fallback(
            "search_repository", repo_name, query_embedding, limit
        )

    def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 5,
        where_filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        return self._execute_with_fallback(
            "search_similar", query_embedding, limit, where_filter
        )

    def search_similar_code(
        self,
        query_embedding: List[float],
        limit: int = 5,
        where_filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        return self.search_similar(query_embedding, limit, where_filter)

    def get_repository_file_paths(self, repo_name: str) -> List[str]:
        return self._execute_with_fallback("get_repository_file_paths", repo_name)

    def get_file_chunks(self, repo_name: str, file_path: str) -> Dict[str, Any]:
        return self._execute_with_fallback("get_file_chunks", repo_name, file_path)

    def add_code_chunks(
        self,
        file_path: str,
        chunks: List[str],
        embeddings: List[List[float]],
        metadata: List[Dict[str, Any]],
    ) -> None:
        """Dual-write code chunks to Primary Qdrant and Fallback Chroma."""
        if self.primary is not None:
            try:
                self.primary.add_code_chunks(file_path, chunks, embeddings, metadata)
            except Exception as exc:
                logger.warning("Primary Qdrant add_code_chunks failed: %s", exc)
        if self.fallback is not None:
            self.fallback.add_code_chunks(file_path, chunks, embeddings, metadata)

    def add_code_chunks_bulk(
        self,
        ids: List[str],
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
    ) -> None:
        """Dual-write code chunks bulk to Primary Qdrant and Fallback Chroma."""
        if self.primary is not None:
            try:
                self.primary.add_code_chunks_bulk(ids, documents, embeddings, metadatas)
            except Exception as exc:
                logger.warning("Primary Qdrant add_code_chunks_bulk failed: %s", exc)
        if self.fallback is not None:
            self.fallback.add_code_chunks_bulk(ids, documents, embeddings, metadatas)

    # --------------------------------------------------------------------------
    # Version-Isolated Staging & Dual-Write Methods
    # --------------------------------------------------------------------------

    def stage_repository_batch(
        self,
        repo_name: str,
        version: str,
        chunks: List[Dict[str, Any]],
        embeddings: List[List[float]],
        start_chunk_id: int = 0,
    ) -> int:
        """Dual-write stage repository batch across Primary and Fallback."""
        primary_ok = False
        if self.primary is not None:
            try:
                if hasattr(self.primary, "stage_repository_batch"):
                    self.primary.stage_repository_batch(
                        repo_name,
                        version,
                        chunks,
                        embeddings,
                        start_chunk_id=start_chunk_id,
                    )
                primary_ok = True
            except Exception as exc:
                logger.warning("Primary stage_repository_batch failed: %s", exc)
                if not self.enable_fallback:
                    raise

        if self.fallback is not None:
            try:
                if hasattr(self.fallback, "stage_repository_batch"):
                    self.fallback.stage_repository_batch(
                        repo_name,
                        version,
                        chunks,
                        embeddings,
                        start_chunk_id=start_chunk_id,
                    )
            except Exception as exc:
                logger.warning("Fallback stage_repository_batch failed: %s", exc)
                if not primary_ok:
                    raise

        return len(chunks)

    def publish_repository_version(
        self,
        repo_name: str,
        version: str,
    ) -> None:
        """Dual-write publish version across Primary and Fallback."""
        primary_ok = False
        if self.primary is not None:
            try:
                if hasattr(self.primary, "publish_repository_version"):
                    self.primary.publish_repository_version(repo_name, version)
                primary_ok = True
            except Exception as exc:
                logger.warning("Primary publish_repository_version failed: %s", exc)
                if not self.enable_fallback:
                    raise

        if self.fallback is not None:
            try:
                if hasattr(self.fallback, "publish_repository_version"):
                    self.fallback.publish_repository_version(repo_name, version)
            except Exception as exc:
                logger.warning("Fallback publish_repository_version failed: %s", exc)
                if not primary_ok:
                    raise

    def rollback_staged_version(
        self,
        repo_name: str,
        version: str,
    ) -> None:
        """Dual-write rollback staged version across Primary and Fallback."""
        if self.primary is not None:
            try:
                if hasattr(self.primary, "rollback_staged_version"):
                    self.primary.rollback_staged_version(repo_name, version)
            except Exception as exc:
                logger.debug("Primary rollback_staged_version error: %s", exc)
        if self.fallback is not None:
            try:
                if hasattr(self.fallback, "rollback_staged_version"):
                    self.fallback.rollback_staged_version(repo_name, version)
            except Exception as exc:
                logger.debug("Fallback rollback_staged_version error: %s", exc)

    # --------------------------------------------------------------------------
    # Dual-Write Ingestion Pipeline (Phase 3.5)
    # --------------------------------------------------------------------------

    def index_repository(
        self,
        repo_name: str,
        chunks: List[Dict[str, Any]],
        embeddings: List[List[float]],
        version: Optional[str] = None,
    ) -> str:
        """Dual-write index repository across Primary Qdrant and Fallback ChromaDB."""
        unified_version = version or uuid.uuid4().hex
        primary_success = False
        primary_err = None
        fallback_success = False
        fallback_err = None

        # 1. Write to Primary (Qdrant)
        if self.primary is not None:
            try:
                self.primary.index_repository(
                    repo_name, chunks, embeddings, version=unified_version
                )
                primary_success = True
            except Exception as exc:
                primary_err = exc
                logger.error(
                    "Dual-write to Primary QdrantStore failed for %s: %s",
                    repo_name,
                    exc,
                )

        # 2. Write to Fallback (ChromaDB)
        if self.fallback is not None:
            try:
                self.fallback.index_repository(
                    repo_name, chunks, embeddings, version=unified_version
                )
                fallback_success = True
            except Exception as exc:
                fallback_err = exc
                logger.error(
                    "Dual-write to Fallback ChromaStore failed for %s: %s",
                    repo_name,
                    exc,
                )

        if primary_success and fallback_success:
            self.telemetry.record_dual_write(success=True)
            logger.info(
                "Dual-write indexing succeeded for %s (version: %s) on both stores.",
                repo_name,
                unified_version,
            )
            return unified_version

        if primary_success and not fallback_success:
            self.telemetry.record_dual_write(success=True)
            logger.warning(
                "Primary Qdrant indexing succeeded for %s but Chroma fallback write failed: %s",
                repo_name,
                fallback_err,
            )
            return unified_version

        if not primary_success and fallback_success:
            self.telemetry.record_dual_write(success=False)
            logger.warning(
                "Primary Qdrant indexing failed for %s (%s); ChromaDB indexed successfully.",
                repo_name,
                primary_err,
            )
            return unified_version

        self.telemetry.record_dual_write(success=False)
        raise RuntimeError(
            f"Dual-write indexing failed on both stores for {repo_name}. "
            f"Primary error: {primary_err}, Fallback error: {fallback_err}"
        )

    def delete_files(self, repo_name: str, file_paths: List[str]) -> None:
        """Dual-write file deletions across both stores."""
        if self.primary is not None:
            try:
                self.primary.delete_files(repo_name, file_paths)
            except Exception as exc:
                logger.warning(
                    "Primary Qdrant delete_files failed for %s: %s", repo_name, exc
                )
        if self.fallback is not None:
            self.fallback.delete_files(repo_name, file_paths)

    def delete_repository(self, repo_name: str) -> None:
        """Dual-write repository deletion across both stores."""
        if self.primary is not None:
            try:
                self.primary.delete_repository(repo_name)
            except Exception as exc:
                logger.warning(
                    "Primary Qdrant delete_repository failed for %s: %s",
                    repo_name,
                    exc,
                )
        if self.fallback is not None:
            self.fallback.delete_repository(repo_name)

    def clear_database(self) -> None:
        """Dual-write clear across both stores."""
        if self.primary is not None:
            try:
                self.primary.clear_database()
            except Exception as exc:
                logger.warning("Primary Qdrant clear_database failed: %s", exc)
        if self.fallback is not None:
            self.fallback.clear_database()
