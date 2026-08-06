"""ChromaDB store module for vector embeddings.

Manages code chunk indexing, file storage, and semantic searches.
"""

import os
import logging
import threading
import time
import uuid
import chromadb
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class ChromaStore:
    """Interface to interact with ChromaDB local client vector database."""

    def __init__(self, persist_directory: str) -> None:
        """Initializes the ChromaStore connection.

        Args:
            persist_directory: Path to the directory where ChromaDB stores its data.
        """
        self.persist_directory = persist_directory
        # Ensure the directory exists
        os.makedirs(self.persist_directory, exist_ok=True)
        self.client = chromadb.PersistentClient(path=self.persist_directory)
        # We create a single collection to store code chunks.
        self.collection = self.client.get_or_create_collection(name="repository_chunks")
        self._versions = self.client.get_or_create_collection(name="repository_index_versions")
        self._publication_lock = threading.RLock()

    def _active_version(self, repo_name: str) -> Optional[str]:
        record = self._versions.get(ids=[repo_name], include=["documents"])
        documents = record.get("documents", []) if record else []
        return documents[0] if documents else None

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
        self._versions.upsert(
            ids=[repo_name],
            documents=[version],
            metadatas=[{"repo_name": repo_name}],
        )

    @staticmethod
    def _clean_metadata(metadata: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        cleaned_metadata = []
        for meta in metadata:
            cleaned = {}
            for key, value in meta.items():
                cleaned[key] = value if isinstance(value, (str, int, float, bool)) else str(value)
            cleaned_metadata.append(cleaned)
        return cleaned_metadata

    def add_code_chunks(
        self,
        file_path: str,
        chunks: List[str],
        embeddings: List[List[float]],
        metadata: List[Dict[str, Any]],
    ) -> None:
        """Adds code chunks with their precomputed embeddings and metadata to ChromaDB.

        Args:
            file_path: Relative or absolute path of the file being indexed.
            chunks: A list of text/code blocks.
            embeddings: Parallel list of float-vector embeddings.
            metadata: Parallel list of dictionaries containing chunk details.
        """
        if not chunks:
            return

        ids = [f"{file_path}_{i}" for i in range(len(chunks))]

        cleaned_metadata = self._clean_metadata(metadata)

        self.collection.add(
            ids=ids, documents=chunks, embeddings=embeddings, metadatas=cleaned_metadata
        )

    def add_code_chunks_bulk(
        self,
        ids: List[str],
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
    ) -> None:
        """Adds code chunks in bulk with their precomputed embeddings and metadata to ChromaDB.

        Args:
            ids: List of unique chunk IDs.
            documents: List of text/code blocks.
            embeddings: Parallel list of float-vector embeddings.
            metadatas: Parallel list of dictionaries containing chunk details.
        """
        if not ids:
            return

        cleaned_metadata = self._clean_metadata(metadatas)
        repo_names = {str(meta.get("repo_name")) for meta in cleaned_metadata if meta.get("repo_name")}
        if len(repo_names) == 1:
            repo_name = next(iter(repo_names))
            with self._publication_lock:
                version = self._active_version(repo_name)
                if version is not None:
                    for meta in cleaned_metadata:
                        meta["index_version"] = version
                self._add_in_batches(ids, documents, embeddings, cleaned_metadata)
            return

        self._add_in_batches(ids, documents, embeddings, cleaned_metadata)

    def _add_in_batches(
        self,
        ids: List[str],
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
    ) -> None:
        """Insert a prepared batch sequence into the chunk collection."""
        batch_size = 2000
        for i in range(0, len(ids), batch_size):
            self.collection.add(
                ids=ids[i : i + batch_size],
                documents=documents[i : i + batch_size],
                embeddings=embeddings[i : i + batch_size],
                metadatas=metadatas[i : i + batch_size],
            )

    def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 5,
        where_filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Performs a vector search to find code chunks similar to the query embedding.

        Args:
            query_embedding: The float vector of the query phrase/code.
            limit: Maximum number of search results.
            where_filter: Key-value dictionary to filter metadata matches.

        Returns:
            A list of dictionary objects representing the matched chunks and their metadata.
        """
        results = self.collection.query(
            query_embeddings=[query_embedding], n_results=limit, where=where_filter
        )

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
        for name in ("repository_chunks", "repository_index_versions"):
            try:
                self.client.delete_collection(name=name)
            except Exception as exc:
                logger.debug("Failed to delete collection %s during clear: %s", name, exc)
        self.collection = self.client.get_or_create_collection(name="repository_chunks")
        self._versions = self.client.get_or_create_collection(name="repository_index_versions")

    def index_repository(
        self,
        repo_name: str,
        chunks: List[Dict[str, Any]],
        embeddings: List[List[float]],
    ) -> None:
        """Stage a complete repository index and publish it only after it is complete."""
        filtered_indices = [
            index
            for index, chunk in enumerate(chunks)
            if isinstance(chunk.get("content", ""), str) and chunk.get("content", "").strip()
        ]
        if embeddings is None or (filtered_indices and len(embeddings) <= max(filtered_indices)):
            raise ValueError("Embeddings must be provided and aligned with chunks.")

        version = uuid.uuid4().hex
        filtered_chunks = [chunks[index] for index in filtered_indices]
        filtered_embeddings = [embeddings[index] for index in filtered_indices]
        ids: List[str] = []
        documents: List[str] = []
        metadatas: List[Dict[str, Any]] = []

        for out_index, chunk in enumerate(filtered_chunks):
            path = chunk.get("path", "")
            chunk_id = chunk.get("chunk_id", out_index)
            ids.append(
                f"{repo_name}_{version}_{path}_{chunk_id}".replace("/", "_").replace(".", "_")
            )
            documents.append(chunk["content"])
            metadatas.append(
                {
                    "repo_name": repo_name,
                    "file_path": path,
                    "chunk_id": chunk_id,
                    "language": chunk.get("language", "text"),
                    "index_version": version,
                }
            )

        try:
            # Staging uses a version not visible to readers, so the active revision
            # remains queryable until the short publish swap below.
            self._add_in_batches(ids, documents, filtered_embeddings, metadatas)
            staged_count = 0
            if ids:
                staged_count = len(
                    self.collection.get(
                        where=self._where_for_repository(repo_name, version),
                        include=["metadatas"],
                    ).get("ids", [])
                )
            if staged_count != len(ids):
                raise RuntimeError("Failed to stage all repository chunks.")

            with self._publication_lock:
                previous_version = self._active_version(repo_name)
                self._publish_version(repo_name, version)
                if previous_version is None:
                    self.collection.delete(
                        where={
                            "$and": [
                                {"repo_name": repo_name},
                                {"index_version": {"$ne": version}},
                            ]
                        }
                    )
                else:
                    self.collection.delete(
                        where=self._where_for_repository(repo_name, previous_version)
                    )
        except Exception:
            try:
                self.collection.delete(
                    where=self._where_for_repository(repo_name, version)
                )
            except Exception as cleanup_error:
                logger.warning("Failed to clean staged index for %s: %s", repo_name, cleanup_error)
            raise

        logger.info("Published %d chunks for repository %s.", len(ids), repo_name)

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
            result = self.collection.get(
                where=self._where_for_repository(repo_name, version), include=["metadatas"]
            )
        return sorted({meta["file_path"] for meta in result.get("metadatas", []) if meta and meta.get("file_path")})

    def get_file_chunks(self, repo_name: str, file_path: str) -> Dict[str, Any]:
        """Return chunks for one file from the currently published revision."""
        with self._publication_lock:
            version = self._active_version(repo_name)
            return self.collection.get(
                where=self._where_for_repository(repo_name, version, file_path),
                include=["documents", "metadatas"],
            )

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
            self.collection.delete(where={"$and": filters})

    def delete_repository(self, repo_name: str) -> None:
        """Delete all revisions associated with a repository."""
        with self._publication_lock:
            self.collection.delete(where={"repo_name": repo_name})
            try:
                self._versions.delete(ids=[repo_name])
            except Exception as exc:
                logger.debug("Repository version %s could not be deleted: %s", repo_name, exc)
