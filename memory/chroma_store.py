"""ChromaDB store module for vector embeddings.

Manages code chunk indexing, file storage, and semantic searches with
narrow collection-level corruption detection, bounded self-healing, and observability.
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, TypeVar

import chromadb
from chromadb.api.models.Collection import Collection

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _is_corrupted_exception(exc: Exception) -> bool:
    """Determine whether an exception indicates vector index / segment corruption.

    Distinguishes internal HNSW segment corruption, broken index readers, or disk
    malformations from expected errors (such as missing items or invalid input).
    """
    err_str = str(exc).lower()
    corruption_markers = (
        "hnsw",
        "segment reader",
        "segment not found",
        "compactor",
        "error loading hnsw index",
        "error constructing hnsw segment reader",
        "corrupted",
        "database disk image is malformed",
        "disk i/o error",
        "memory allocation of",
        "cannot open file",
        "database is locked",
    )
    if isinstance(exc, getattr(chromadb.errors, "InternalError", Exception)):
        return True
    return any(marker in err_str for marker in corruption_markers)


class ChromaStore:
    """Interface to interact with ChromaDB local client vector database.

    Provides collection-level corruption detection, self-healing recovery,
    versioned index publication, and concurrency safety.
    """

    def __init__(self, persist_directory: str) -> None:
        """Initializes the ChromaStore connection.

        Args:
            persist_directory: Path to the directory where ChromaDB stores its data.
        """
        self.persist_directory = persist_directory
        os.makedirs(self.persist_directory, exist_ok=True)
        self.client = chromadb.PersistentClient(path=self.persist_directory)
        self._publication_lock = threading.RLock()
        self._init_collections()

    def _init_collections(self) -> None:
        """Initialize collections and verify health via safe probing with auto-recovery."""
        with self._publication_lock:
            # 1. Main chunk collection
            try:
                self.collection = self.client.get_or_create_collection(
                    name="repository_chunks"
                )
                self.collection.count()
            except Exception as exc:
                if _is_corrupted_exception(exc):
                    logger.error(
                        "[CHROMA_RECOVERY] collection=repository_chunks operation=init reason=%s action=reset_storage_directory",
                        exc,
                    )
                    self.collection = self._reset_storage_directory("repository_chunks")
                else:
                    raise

            # 2. Version metadata collection
            try:
                self._versions = self.client.get_or_create_collection(
                    name="repository_index_versions"
                )
                self._versions.count()
            except Exception as exc:
                if _is_corrupted_exception(exc):
                    logger.error(
                        "[CHROMA_RECOVERY] collection=repository_index_versions operation=init reason=%s action=reset_storage_directory",
                        exc,
                    )
                    self._versions = self._reset_storage_directory(
                        "repository_index_versions"
                    )
                else:
                    raise

    def _recreate_collection_internal(self, name: str) -> Collection:
        """Safely recreate a single collection. Falls back to directory recovery if unreadable."""
        logger.warning(
            "[CHROMA_RECOVERY] collection=%s reason=corruption_detected action=recreate_collection",
            name,
        )
        try:
            self.client.delete_collection(name=name)
            new_col = self.client.get_or_create_collection(name=name)
            new_col.count()
            if name == "repository_chunks":
                self.collection = new_col
            elif name == "repository_index_versions":
                self._versions = new_col
            return new_col
        except Exception as del_exc:
            logger.error(
                "[CHROMA_RECOVERY] collection=%s deletion_failed=%s action=database_directory_reset",
                name,
                del_exc,
            )
            return self._reset_storage_directory(name)

    def _reset_storage_directory(self, target_collection: str) -> Collection:
        """Reset corrupted storage directory with timestamped backup when collection deletion fails."""
        backup_dir = f"{self.persist_directory}_corrupted_backup_{int(time.time())}"
        logger.warning(
            "[CHROMA_RECOVERY] directory=%s backup=%s reason=unrecoverable_sqlite_corruption action=recreate_directory",
            self.persist_directory,
            backup_dir,
        )
        try:
            self.client = None
            if os.path.exists(self.persist_directory):
                # Try atomic rename to preserve backup for diagnostics
                shutil.move(self.persist_directory, backup_dir)
        except Exception as move_exc:
            logger.error(
                "Could not move corrupted chroma directory (%s). Cleaning files...",
                move_exc,
            )
            if os.path.exists(self.persist_directory):
                for item in os.listdir(self.persist_directory):
                    item_path = os.path.join(self.persist_directory, item)
                    try:
                        if os.path.isdir(item_path):
                            shutil.rmtree(item_path, ignore_errors=True)
                        else:
                            os.remove(item_path)
                    except Exception:
                        pass

        os.makedirs(self.persist_directory, exist_ok=True)
        self.client = chromadb.PersistentClient(path=self.persist_directory)
        self.collection = self.client.get_or_create_collection(name="repository_chunks")
        self._versions = self.client.get_or_create_collection(
            name="repository_index_versions"
        )
        return (
            self.collection
            if target_collection == "repository_chunks"
            else self._versions
        )

    def _execute_with_recovery(
        self,
        collection_name: str,
        operation_name: str,
        fn: Callable[[], T],
        max_retries: int = 1,
    ) -> T:
        """Execute a collection operation with bounded corruption recovery."""
        attempts = 0
        while True:
            try:
                return fn()
            except Exception as exc:
                attempts += 1
                if attempts <= max_retries and _is_corrupted_exception(exc):
                    logger.error(
                        "[CHROMA_RECOVERY] collection=%s operation=%s reason=%s action=recreate_collection (attempt %d/%d)",
                        collection_name,
                        operation_name,
                        exc,
                        attempts,
                        max_retries,
                    )
                    with self._publication_lock:
                        self._recreate_collection_internal(collection_name)
                    continue
                raise

    def _active_version(self, repo_name: str) -> Optional[str]:
        def _get():
            record = self._versions.get(ids=[repo_name], include=["documents"])
            documents = record.get("documents", []) if record else []
            return documents[0] if documents else None

        try:
            return self._execute_with_recovery(
                "repository_index_versions", "active_version", _get
            )
        except Exception as exc:
            logger.warning(
                "Failed to resolve active version for %s: %s", repo_name, exc
            )
            return None

    @staticmethod
    def _where_for_repository(
        repo_name: str,
        version: Optional[str],
        file_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        filters: List[Dict[str, Any]] = [{"repo_name": repo_name}]
        if version is not None:
            filters.append({"index_version": version})
        if file_path is not None:
            filters.append({"file_path": file_path})
        return filters[0] if len(filters) == 1 else {"$and": filters}

    def _publish_version(self, repo_name: str, version: str) -> None:
        def _upsert():
            self._versions.upsert(
                ids=[repo_name],
                documents=[version],
                metadatas=[{"repo_name": repo_name}],
            )

        self._execute_with_recovery(
            "repository_index_versions", "publish_version", _upsert
        )

    @staticmethod
    def _clean_metadata(metadata: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        cleaned_metadata = []
        for meta in metadata:
            cleaned = {}
            for key, value in meta.items():
                cleaned[key] = (
                    value if isinstance(value, (str, int, float, bool)) else str(value)
                )
            cleaned_metadata.append(cleaned)
        return cleaned_metadata

    def add_code_chunks(
        self,
        file_path: str,
        chunks: List[str],
        embeddings: List[List[float]],
        metadata: List[Dict[str, Any]],
    ) -> None:
        """Adds code chunks with their precomputed embeddings and metadata to ChromaDB."""
        if not chunks:
            return

        ids = [f"{file_path}_{i}" for i in range(len(chunks))]
        cleaned_metadata = self._clean_metadata(metadata)
        for meta in cleaned_metadata:
            r_name = meta.get("repo_name")
            if r_name and "index_version" not in meta:
                with self._publication_lock:
                    v = self._active_version(str(r_name))
                if v is not None:
                    meta["index_version"] = v

        def _upsert():
            self.collection.upsert(
                ids=ids,
                documents=chunks,
                embeddings=embeddings,
                metadatas=cleaned_metadata,
            )

        self._execute_with_recovery("repository_chunks", "add_code_chunks", _upsert)

    def add_code_chunks_bulk(
        self,
        ids: List[str],
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
    ) -> None:
        """Adds code chunks in bulk with their precomputed embeddings and metadata to ChromaDB."""
        if not ids:
            return

        cleaned_metadata = self._clean_metadata(metadatas)
        for meta in cleaned_metadata:
            r_name = meta.get("repo_name")
            if r_name and "index_version" not in meta:
                with self._publication_lock:
                    v = self._active_version(str(r_name))
                if v is not None:
                    meta["index_version"] = v

        self._add_in_batches(ids, documents, embeddings, cleaned_metadata)

    def _add_in_batches(
        self,
        ids: List[str],
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
    ) -> None:
        """Insert a prepared batch sequence into the chunk collection safely using upsert."""
        seen_ids = set()
        unique_ids = []
        unique_docs = []
        unique_embs = []
        unique_metas = []
        for idx, uid in enumerate(ids):
            if uid not in seen_ids:
                seen_ids.add(uid)
                unique_ids.append(uid)
                unique_docs.append(documents[idx])
                unique_embs.append(embeddings[idx])
                unique_metas.append(metadatas[idx])

        batch_size = 2000
        for i in range(0, len(unique_ids), batch_size):
            b_ids = unique_ids[i : i + batch_size]
            b_docs = unique_docs[i : i + batch_size]
            b_embs = unique_embs[i : i + batch_size]
            b_metas = unique_metas[i : i + batch_size]

            def _batch_add():
                self.collection.add(
                    ids=b_ids,
                    documents=b_docs,
                    embeddings=b_embs,
                    metadatas=b_metas,
                )

            self._execute_with_recovery("repository_chunks", "add_batch", _batch_add)

    def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 5,
        where_filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Performs a vector search to find code chunks similar to the query embedding."""

        def _query():
            return self.collection.query(
                query_embeddings=[query_embedding], n_results=limit, where=where_filter
            )

        try:
            results = self._execute_with_recovery(
                "repository_chunks", "search_similar", _query
            )
        except Exception as exc:
            logger.warning("Vector search query failed: %s", exc)
            return []

        formatted_results = []
        if results and "documents" in results and results["documents"]:
            docs = results["documents"][0]
            metas = (
                results["metadatas"][0]
                if "metadatas" in results and results["metadatas"]
                else [{}] * len(docs)
            )
            ids = (
                results["ids"][0]
                if "ids" in results and results["ids"]
                else [""] * len(docs)
            )
            distances = (
                results["distances"][0]
                if "distances" in results and results["distances"]
                else [0.0] * len(docs)
            )

            for doc, meta, idx, dist in zip(docs, metas, ids, distances):
                formatted_results.append(
                    {"id": idx, "content": doc, "metadata": meta, "distance": dist}
                )

        return formatted_results

    def search_similar_code(
        self,
        query_embedding: List[float],
        limit: int = 5,
        where_filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Backward-compatible alias for :meth:`search_similar`."""
        return self.search_similar(query_embedding, limit, where_filter)

    def clear_database(self) -> None:
        """Deletes all collections and clears current vector index storage."""
        try:
            from services.chat.retrieval_cache import retrieval_cache

            retrieval_cache.invalidate_all()
        except ImportError:
            pass

        with self._publication_lock:
            for name in ("repository_chunks", "repository_index_versions"):
                try:
                    self.client.delete_collection(name=name)
                except Exception as exc:
                    logger.debug(
                        "Failed to delete collection %s during clear: %s", name, exc
                    )
            self.collection = self.client.get_or_create_collection(
                name="repository_chunks"
            )
            self._versions = self.client.get_or_create_collection(
                name="repository_index_versions"
            )

    def stage_repository_batch(
        self,
        repo_name: str,
        version: str,
        chunks: List[Dict[str, Any]],
        embeddings: List[List[float]],
        start_chunk_id: int = 0,
    ) -> int:
        """Stage a batch of chunks for a repository version in ChromaStore."""
        filtered_indices = [
            index
            for index, chunk in enumerate(chunks)
            if isinstance(chunk.get("content", ""), str)
            and chunk.get("content", "").strip()
        ]
        if embeddings is None or (
            filtered_indices and len(embeddings) <= max(filtered_indices)
        ):
            raise ValueError("Embeddings must be provided and aligned with chunks.")

        filtered_chunks = [chunks[index] for index in filtered_indices]
        filtered_embeddings = [embeddings[index] for index in filtered_indices]
        ids: List[str] = []
        documents: List[str] = []
        metadatas: List[Dict[str, Any]] = []

        for out_index, chunk in enumerate(filtered_chunks):
            path = chunk.get("path") or chunk.get("file_path", "")
            chunk_id = chunk.get("chunk_id", start_chunk_id + out_index)
            ids.append(
                f"{repo_name}_{version}_{path}_{chunk_id}".replace("/", "_").replace(
                    ".", "_"
                )
            )
            documents.append(chunk["content"])
            metadatas.append(
                {
                    "repo_name": repo_name,
                    "file_path": path,
                    "chunk_id": chunk_id,
                    "language": chunk.get("language", "text"),
                    "category": chunk.get("category", "production"),
                    "source_priority": float(chunk.get("source_priority", 1.0)),
                    "is_entry_point": bool(chunk.get("is_entry_point", False)),
                    "index_version": version,
                }
            )

        if ids:
            self._add_in_batches(ids, documents, filtered_embeddings, metadatas)
        return len(ids)

    def publish_repository_version(
        self,
        repo_name: str,
        version: str,
    ) -> None:
        """Publish staged repository version and delete previous version."""
        with self._publication_lock:
            previous_version = self._active_version(repo_name)
            self._publish_version(repo_name, version)

            def _clean_old():
                if previous_version is None:
                    self.collection.delete(
                        where={
                            "$and": [
                                {"repo_name": repo_name},
                                {"index_version": {"$ne": version}},
                            ]
                        }
                    )
                elif previous_version != version:
                    self.collection.delete(
                        where=self._where_for_repository(repo_name, previous_version)
                    )

            try:
                self._execute_with_recovery(
                    "repository_chunks", "publish_cleanup", _clean_old
                )
            except Exception as exc:
                logger.warning(
                    "Non-fatal error cleaning old index version for %s: %s",
                    repo_name,
                    exc,
                )

        try:
            from services.chat.retrieval_cache import retrieval_cache

            retrieval_cache.invalidate_repo(repo_name)
        except ImportError:
            pass

    def rollback_staged_version(
        self,
        repo_name: str,
        version: str,
    ) -> None:
        """Clean up staged chunks if indexing failed before publication."""
        try:

            def _rollback():
                self.collection.delete(
                    where=self._where_for_repository(repo_name, version)
                )

            self._execute_with_recovery(
                "repository_chunks", "rollback_staged", _rollback
            )
        except Exception as cleanup_error:
            logger.warning(
                "Failed to clean staged index for %s: %s", repo_name, cleanup_error
            )

    def index_repository(
        self,
        repo_name: str,
        chunks: List[Dict[str, Any]],
        embeddings: List[List[float]],
        version: Optional[str] = None,
    ) -> str:
        """Stage a complete repository index and publish it only after it is complete."""
        version = version or uuid.uuid4().hex
        try:
            staged_count = self.stage_repository_batch(
                repo_name, version, chunks, embeddings
            )
            self.publish_repository_version(repo_name, version)
            logger.info(
                "Published %d chunks for repository %s.", staged_count, repo_name
            )
            return version
        except Exception:
            self.rollback_staged_version(repo_name, version)
            raise

    def _search_repository(
        self, repo_name: str, query_embedding: List[float], limit: int
    ) -> List[Dict[str, Any]]:
        version = self._active_version(repo_name)
        return self.search_similar(
            query_embedding=query_embedding,
            limit=limit,
            where_filter=self._where_for_repository(repo_name, version),
        )

    def search_repository(
        self, repo_name: str, query_embedding: List[float], limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Search the currently published revision of a repository."""
        with self._publication_lock:
            return self._search_repository(repo_name, query_embedding, limit)

    def get_repository_file_paths(self, repo_name: str) -> List[str]:
        """Return paths from the currently published repository revision."""
        with self._publication_lock:
            version = self._active_version(repo_name)

            def _get_paths():
                return self.collection.get(
                    where=self._where_for_repository(repo_name, version),
                    include=["metadatas"],
                )

            try:
                result = self._execute_with_recovery(
                    "repository_chunks", "get_file_paths", _get_paths
                )
            except Exception as exc:
                logger.warning("Failed to get file paths for %s: %s", repo_name, exc)
                return []

        return sorted(
            {
                meta["file_path"]
                for meta in result.get("metadatas", [])
                if meta and meta.get("file_path")
            }
        )

    def get_file_chunks(self, repo_name: str, file_path: str) -> Dict[str, Any]:
        """Return chunks for one file from the currently published revision."""
        with self._publication_lock:
            version = self._active_version(repo_name)

            def _get_chunks():
                return self.collection.get(
                    where=self._where_for_repository(repo_name, version, file_path),
                    include=["documents", "metadatas"],
                )

            try:
                return self._execute_with_recovery(
                    "repository_chunks", "get_file_chunks", _get_chunks
                )
            except Exception as exc:
                logger.warning(
                    "Failed to get file chunks for %s (%s): %s",
                    repo_name,
                    file_path,
                    exc,
                )
                return {"documents": [], "metadatas": []}

    def delete_files(self, repo_name: str, file_paths: List[str]) -> None:
        """Remove paths from the currently published repository revision."""
        if not file_paths:
            return
        with self._publication_lock:
            version = self._active_version(repo_name)
            filters: List[Dict[str, Any]] = [
                {"repo_name": repo_name},
                {"file_path": {"$in": file_paths}},
            ]
            if version is not None:
                filters.append({"index_version": version})

            def _delete():
                self.collection.delete(where={"$and": filters})

            try:
                self._execute_with_recovery(
                    "repository_chunks", "delete_files", _delete
                )
            except Exception as exc:
                logger.warning(
                    "Non-fatal delete_files error for %s: %s", repo_name, exc
                )

        try:
            from services.chat.retrieval_cache import retrieval_cache

            retrieval_cache.invalidate_repo(repo_name)
        except ImportError:
            pass

    def delete_repository(self, repo_name: str) -> None:
        """Delete all revisions associated with a repository."""
        with self._publication_lock:

            def _delete_chunks():
                self.collection.delete(where={"repo_name": repo_name})

            try:
                self._execute_with_recovery(
                    "repository_chunks", "delete_repository", _delete_chunks
                )
            except Exception as exc:
                logger.warning(
                    "Non-fatal error deleting repository chunks for %s: %s",
                    repo_name,
                    exc,
                )

            try:

                def _delete_versions():
                    self._versions.delete(ids=[repo_name])

                self._execute_with_recovery(
                    "repository_index_versions",
                    "delete_repo_versions",
                    _delete_versions,
                )
            except Exception as exc:
                logger.debug(
                    "Repository version %s could not be deleted: %s", repo_name, exc
                )

        try:
            from services.chat.retrieval_cache import retrieval_cache

            retrieval_cache.invalidate_repo(repo_name)
        except ImportError:
            pass

    def get_indexed_files(self, repo_name: str) -> List[str]:
        """Return list of distinct file paths indexed for the active repository revision."""
        with self._publication_lock:
            version = self._active_version(repo_name)
            where_clause: Dict[str, Any] = {"repo_name": repo_name}
            if version is not None:
                where_clause = {
                    "$and": [{"repo_name": repo_name}, {"index_version": version}]
                }

            def _get():
                return self.collection.get(where=where_clause, include=["metadatas"])

            try:
                results = self._execute_with_recovery(
                    "repository_chunks", "get_indexed_files", _get
                )
                metadatas = results.get("metadatas") or []
                files = {
                    m.get("file_path") for m in metadatas if m and m.get("file_path")
                }
                return sorted(list(files))
            except Exception as exc:
                logger.debug("Failed to get indexed files for %s: %s", repo_name, exc)
                return []
