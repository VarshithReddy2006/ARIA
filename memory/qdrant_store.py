"""Qdrant store module for vector embeddings (Phase 2C POC).

Provides a dedicated/isolated vector database interface implementing the exact
same method contracts and ranking semantics as ChromaStore.
"""

from __future__ import annotations

import logging
import os
import threading
import uuid
from typing import Any, Dict, List, Optional

try:
    from qdrant_client import QdrantClient, models
    from qdrant_client.models import (
        Distance,
        FieldCondition,
        Filter,
        MatchValue,
        PointStruct,
        VectorParams,
    )
except ImportError:
    QdrantClient = None
    models = None
    Distance = None
    FieldCondition = None
    Filter = None
    MatchValue = None
    PointStruct = None
    VectorParams = None

logger = logging.getLogger(__name__)

COLLECTION_CHUNKS = "repository_chunks"
COLLECTION_VERSIONS = "repository_index_versions"


class QdrantStore:
    """Isolated Qdrant vector database store implementing ChromaStore contracts."""

    def __init__(
        self,
        persist_directory: Optional[str] = "data/qdrant_db",
        url: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        grpc_port: Optional[int] = None,
        prefer_grpc: bool = False,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
        vector_size: int = 384,
    ) -> None:
        """Initializes the QdrantStore connection.

        Args:
            persist_directory: Path to local persistent storage directory (or ':memory:').
            url: URL of standalone Qdrant server (e.g. 'http://localhost:6333' or remote cloud URL).
            host: Hostname of standalone Qdrant server.
            port: HTTP port of standalone Qdrant server.
            grpc_port: gRPC port of standalone Qdrant server.
            prefer_grpc: Whether to prefer gRPC over HTTP for vector operations.
            api_key: API key for remote Qdrant authentication.
            timeout: Network request timeout in seconds.
            vector_size: Dimensionality of vector embeddings (default: 384 for BGE-small).
        """
        if QdrantClient is None:
            raise ImportError(
                "qdrant-client package is required to use QdrantStore. "
                "Install it with 'pip install qdrant-client'."
            )

        self.persist_directory = persist_directory
        self.url = url
        self.api_key = api_key
        self.timeout = timeout
        self.vector_size = vector_size
        self._publication_lock = threading.RLock()
        self._collections_lock = threading.RLock()
        self._collections_ensured = False
        self._version_cache: Dict[str, str] = {}

        client_kwargs: Dict[str, Any] = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        if timeout:
            client_kwargs["timeout"] = timeout

        if url:
            self.client = QdrantClient(
                url=url, prefer_grpc=prefer_grpc, **client_kwargs
            )
        elif host and port:
            self.client = QdrantClient(
                host=host,
                port=port,
                grpc_port=grpc_port,
                prefer_grpc=prefer_grpc,
                **client_kwargs,
            )
        elif persist_directory == ":memory:":
            self.client = QdrantClient(":memory:", **client_kwargs)
        else:
            os.makedirs(str(self.persist_directory), exist_ok=True)
            self.client = QdrantClient(path=self.persist_directory)

    def _ensure_collections(self) -> None:
        """Ensure collections and payload indexes exist (lazy initialization)."""
        if self._collections_ensured:
            return
        with self._collections_lock:
            if self._collections_ensured:
                return
            try:
                if not VectorParams or not Distance or not models:
                    return
                existing = [c.name for c in self.client.get_collections().collections]
                if COLLECTION_CHUNKS not in existing:
                    self.client.create_collection(
                        collection_name=COLLECTION_CHUNKS,
                        vectors_config=VectorParams(
                            size=self.vector_size,
                            distance=Distance.COSINE,
                        ),
                    )
                    # Create payload indexes for fast filtering (relevant when running client-server)
                    import warnings

                    for field in (
                        "repo_name",
                        "index_version",
                        "file_path",
                        "language",
                    ):
                        try:
                            with warnings.catch_warnings():
                                warnings.simplefilter("ignore", UserWarning)
                                self.client.create_payload_index(
                                    collection_name=COLLECTION_CHUNKS,
                                    field_name=field,
                                    field_schema=models.PayloadSchemaType.KEYWORD,
                                )
                        except Exception as exc:
                            logger.debug(
                                "Payload index creation for %s: %s", field, exc
                            )

                # 2. Versions collection
                if COLLECTION_VERSIONS not in existing:
                    self.client.create_collection(
                        collection_name=COLLECTION_VERSIONS,
                        vectors_config=VectorParams(
                            size=1,  # Dummy vector for version tracking collection
                            distance=Distance.DOT,
                        ),
                    )
                    try:
                        self.client.create_payload_index(
                            collection_name=COLLECTION_VERSIONS,
                            field_name="repo_name",
                            field_schema=models.PayloadSchemaType.KEYWORD,
                        )
                    except Exception as exc:
                        logger.debug("Payload index creation for versions: %s", exc)
                self._collections_ensured = True
            except Exception as exc:
                logger.warning(
                    "Could not connect to Qdrant to ensure collections: %s", exc
                )
                return

    def _active_version(self, repo_name: str) -> Optional[str]:
        """Fetch active index version for a repository."""
        self._ensure_collections()
        if repo_name in self._version_cache:
            return self._version_cache[repo_name]

        try:
            scroll_result = self.client.scroll(
                collection_name=COLLECTION_VERSIONS,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="repo_name", match=MatchValue(value=repo_name)
                        )
                    ]
                ),
                limit=1,
                with_payload=True,
            )
            points = scroll_result[0]
            if points and points[0].payload:
                version = points[0].payload.get("version")
                if version:
                    self._version_cache[repo_name] = version
                return version
        except Exception as exc:
            logger.debug("Failed to fetch active version for %s: %s", repo_name, exc)
        return None

    def _publish_version(self, repo_name: str, version: str) -> None:
        """Publish new active index version for a repository."""
        self._version_cache[repo_name] = version
        # Deterministic UUID for the repo_name in version collection
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"version_{repo_name}"))
        self.client.upsert(
            collection_name=COLLECTION_VERSIONS,
            points=[
                PointStruct(
                    id=point_id,
                    vector=[0.0],
                    payload={"repo_name": repo_name, "version": version},
                )
            ],
        )

    def clear_database(self) -> None:
        """Clears all vectors and collections in Qdrant."""
        self._version_cache.clear()
        try:
            from services.chat.retrieval_cache import retrieval_cache

            retrieval_cache.invalidate_all()
        except ImportError:
            pass
        for name in (COLLECTION_CHUNKS, COLLECTION_VERSIONS):
            try:
                self.client.delete_collection(collection_name=name)
            except Exception as exc:
                logger.debug("Failed to delete Qdrant collection %s: %s", name, exc)
        self._ensure_collections()

    @staticmethod
    def _build_filter(
        repo_name: Optional[str] = None,
        version: Optional[str] = None,
        file_path: Optional[str] = None,
        where_filter: Optional[Dict[str, Any]] = None,
    ) -> Optional[Filter]:
        """Translate filter parameters / dictionary into Qdrant Filter."""
        must_conditions = []
        if repo_name:
            must_conditions.append(
                FieldCondition(key="repo_name", match=MatchValue(value=repo_name))
            )
        if version:
            must_conditions.append(
                FieldCondition(key="index_version", match=MatchValue(value=version))
            )
        if file_path:
            must_conditions.append(
                FieldCondition(key="file_path", match=MatchValue(value=file_path))
            )

        if where_filter:
            # Handle simple dict filters or $and structures
            def parse_condition(k: str, v: Any):
                if isinstance(v, (str, int, bool)):
                    must_conditions.append(
                        FieldCondition(key=k, match=MatchValue(value=v))
                    )

            if "$and" in where_filter and isinstance(where_filter["$and"], list):
                for sub in where_filter["$and"]:
                    for k, v in sub.items():
                        parse_condition(k, v)
            else:
                for k, v in where_filter.items():
                    parse_condition(k, v)

        return Filter(must=must_conditions) if must_conditions else None

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
        """Adds code chunks with their precomputed embeddings and metadata."""
        if not chunks:
            return

        self._ensure_collections()
        ids = [f"{file_path}_{i}" for i in range(len(chunks))]
        cleaned_metadata = self._clean_metadata(metadata)
        with self._publication_lock:
            for meta in cleaned_metadata:
                r_name = meta.get("repo_name")
                if r_name and "index_version" not in meta:
                    v = self._active_version(str(r_name))
                    if v is not None:
                        meta["index_version"] = v

            points = []
            for uid, chunk, emb, meta in zip(ids, chunks, embeddings, cleaned_metadata):
                point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, uid))
                payload = dict(meta)
                payload["_document"] = chunk
                payload["_original_id"] = uid
                points.append(PointStruct(id=point_id, vector=emb, payload=payload))

            self.client.upsert(collection_name=COLLECTION_CHUNKS, points=points)

    def add_code_chunks_bulk(
        self,
        ids: List[str],
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
    ) -> None:
        """Adds code chunks in bulk with their precomputed embeddings and metadata."""
        if not ids:
            return

        self._ensure_collections()
        cleaned_metadata = self._clean_metadata(metadatas)
        with self._publication_lock:
            for meta in cleaned_metadata:
                r_name = meta.get("repo_name")
                if r_name and "index_version" not in meta:
                    v = self._active_version(str(r_name))
                    if v is not None:
                        meta["index_version"] = v

            points = []
            for uid, doc, emb, meta in zip(
                ids, documents, embeddings, cleaned_metadata
            ):
                point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, uid))
                payload = dict(meta)
                payload["_document"] = doc
                payload["_original_id"] = uid
                points.append(PointStruct(id=point_id, vector=emb, payload=payload))

            batch_size = 500
            for i in range(0, len(points), batch_size):
                self.client.upsert(
                    collection_name=COLLECTION_CHUNKS,
                    points=points[i : i + batch_size],
                )

    def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 5,
        where_filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Performs vector search matching ChromaStore output format."""
        with self._publication_lock:
            qdrant_filter = self._build_filter(where_filter=where_filter)
            search_result = self.client.query_points(
                collection_name=COLLECTION_CHUNKS,
                query=query_embedding,
                query_filter=qdrant_filter,
                limit=limit,
                with_payload=True,
            )

            formatted_results = []
            for point in search_result.points:
                payload = point.payload or {}
                doc = payload.get("_document", "")
                orig_id = payload.get("_original_id", str(point.id))
                meta = {k: v for k, v in payload.items() if not k.startswith("_")}
                distance = max(
                    0.0,
                    round(1.0 - (point.score if point.score is not None else 1.0), 4),
                )
                formatted_results.append(
                    {
                        "id": orig_id,
                        "content": doc,
                        "metadata": meta,
                        "distance": distance,
                    }
                )

            return formatted_results

    def search_repository(
        self, repo_name: str, query_embedding: List[float], limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Search the currently published revision of a repository."""
        with self._publication_lock:
            version = self._active_version(repo_name)
            qdrant_filter = self._build_filter(repo_name=repo_name, version=version)
            search_result = self.client.query_points(
                collection_name=COLLECTION_CHUNKS,
                query=query_embedding,
                query_filter=qdrant_filter,
                limit=limit,
                with_payload=True,
            )

            formatted_results = []
            for point in search_result.points:
                payload = point.payload or {}
                doc = payload.get("_document", "")
                orig_id = payload.get("_original_id", str(point.id))
                meta = {k: v for k, v in payload.items() if not k.startswith("_")}
                distance = max(
                    0.0,
                    round(1.0 - (point.score if point.score is not None else 1.0), 4),
                )
                formatted_results.append(
                    {
                        "id": orig_id,
                        "content": doc,
                        "metadata": meta,
                        "distance": distance,
                    }
                )
            return formatted_results

    def get_repository_file_paths(self, repo_name: str) -> List[str]:
        """Return unique file paths from published revision."""
        with self._publication_lock:
            version = self._active_version(repo_name)
            qdrant_filter = self._build_filter(repo_name=repo_name, version=version)
            scroll_result = self.client.scroll(
                collection_name=COLLECTION_CHUNKS,
                scroll_filter=qdrant_filter,
                limit=10000,
                with_payload=["file_path"],
                with_vectors=False,
            )
            points = scroll_result[0]
            paths = set()
            for p in points:
                if p.payload and "file_path" in p.payload:
                    paths.add(p.payload["file_path"])
            return sorted(paths)

    def get_file_chunks(self, repo_name: str, file_path: str) -> Dict[str, Any]:
        """Return all chunks for a specific file in a repository."""
        with self._publication_lock:
            version = self._active_version(repo_name)
            qdrant_filter = self._build_filter(
                repo_name=repo_name, version=version, file_path=file_path
            )
            scroll_result = self.client.scroll(
                collection_name=COLLECTION_CHUNKS,
                scroll_filter=qdrant_filter,
                limit=1000,
                with_payload=True,
                with_vectors=False,
            )
            points = scroll_result[0]
            docs, metas, ids = [], [], []
            for p in points:
                payload = p.payload or {}
                docs.append(payload.get("_document", ""))
                ids.append(payload.get("_original_id", str(p.id)))
                metas.append(
                    {k: v for k, v in payload.items() if not k.startswith("_")}
                )
            return {"documents": docs, "metadatas": metas, "ids": ids}

    def stage_repository_batch(
        self,
        repo_name: str,
        version: str,
        chunks: List[Dict[str, Any]],
        embeddings: List[List[float]],
        start_chunk_id: int = 0,
    ) -> int:
        """Stage a batch of chunks for a repository version. Returns count of staged chunks."""
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
            self.add_code_chunks_bulk(ids, documents, filtered_embeddings, metadatas)
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
            if previous_version is not None and previous_version != version:
                try:
                    self.client.delete(
                        collection_name=COLLECTION_CHUNKS,
                        points_selector=models.FilterSelector(
                            filter=Filter(
                                must=[
                                    FieldCondition(
                                        key="repo_name",
                                        match=MatchValue(value=repo_name),
                                    ),
                                    FieldCondition(
                                        key="index_version",
                                        match=MatchValue(value=previous_version),
                                    ),
                                ]
                            )
                        ),
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to delete previous index version %s for %s: %s",
                        previous_version,
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
            self.client.delete(
                collection_name=COLLECTION_CHUNKS,
                points_selector=models.FilterSelector(
                    filter=Filter(
                        must=[
                            FieldCondition(
                                key="repo_name", match=MatchValue(value=repo_name)
                            ),
                            FieldCondition(
                                key="index_version", match=MatchValue(value=version)
                            ),
                        ]
                    )
                ),
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
        """Stage a complete repository index and publish it only after staging succeeds."""
        version = version or uuid.uuid4().hex
        try:
            staged_count = self.stage_repository_batch(
                repo_name, version, chunks, embeddings
            )
            self.publish_repository_version(repo_name, version)
            logger.info(
                "Published %d chunks for repository %s in Qdrant.",
                staged_count,
                repo_name,
            )
            return version
        except Exception:
            self.rollback_staged_version(repo_name, version)
            raise

    def delete_files(self, repo_name: str, file_paths: List[str]) -> None:
        """Remove paths from the currently published repository revision in Qdrant."""
        if not file_paths:
            return
        with self._publication_lock:
            version = self._active_version(repo_name)
            conditions = [
                FieldCondition(key="repo_name", match=MatchValue(value=repo_name)),
            ]
            if version is not None:
                conditions.append(
                    FieldCondition(key="index_version", match=MatchValue(value=version))
                )
            for fp in file_paths:
                conds = list(conditions) + [
                    FieldCondition(key="file_path", match=MatchValue(value=fp))
                ]
                try:
                    self.client.delete(
                        collection_name=COLLECTION_CHUNKS,
                        points_selector=models.FilterSelector(
                            filter=Filter(must=conds)
                        ),
                    )
                except Exception as exc:
                    logger.debug(
                        "Failed to delete points for %s:%s: %s", repo_name, fp, exc
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
            conditions = [
                FieldCondition(key="repo_name", match=MatchValue(value=repo_name)),
            ]
            if version is not None:
                conditions.append(
                    FieldCondition(key="index_version", match=MatchValue(value=version))
                )
            try:
                points, _ = self.client.scroll(
                    collection_name=COLLECTION_CHUNKS,
                    scroll_filter=Filter(must=conditions),
                    limit=10000,
                    with_payload=True,
                    with_vectors=False,
                )
                files = set()
                for pt in points:
                    payload = pt.payload or {}
                    fp = payload.get("file_path")
                    if fp:
                        files.add(fp)
                return sorted(list(files))
            except Exception as exc:
                logger.debug("Failed to get indexed files for %s: %s", repo_name, exc)
                return []

    def delete_repository(self, repo_name: str) -> None:
        """Delete all revisions associated with a repository from Qdrant."""
        with self._publication_lock:
            try:
                self.client.delete(
                    collection_name=COLLECTION_CHUNKS,
                    points_selector=models.FilterSelector(
                        filter=Filter(
                            must=[
                                FieldCondition(
                                    key="repo_name", match=MatchValue(value=repo_name)
                                )
                            ]
                        )
                    ),
                )
            except Exception as exc:
                logger.debug("Failed to delete chunks for %s: %s", repo_name, exc)

            try:
                version_point_id = str(
                    uuid.uuid5(uuid.NAMESPACE_DNS, f"version_{repo_name}")
                )
                self.client.delete(
                    collection_name=COLLECTION_VERSIONS,
                    points_selector=models.PointIdsList(points=[version_point_id]),
                )
                self._version_cache.pop(repo_name, None)
            except Exception as exc:
                logger.debug("Failed to delete version for %s: %s", repo_name, exc)
        try:
            from services.chat.retrieval_cache import retrieval_cache

            retrieval_cache.invalidate_repo(repo_name)
        except ImportError:
            pass
