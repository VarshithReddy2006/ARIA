"""Unit tests for memory module (ChromaStore)."""

import os
import shutil
import pytest
from memory import ChromaStore


@pytest.fixture
def chroma_test_dir(tmp_path):
    """Provides a clean temporary directory for ChromaDB storage tests."""
    test_dir = os.path.join(tmp_path, "chroma_test_db")
    yield test_dir
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir, ignore_errors=True)


def test_chroma_store_basic_operations(chroma_test_dir) -> None:
    """Verifies vector storage, querying, filtering, and deletion in ChromaStore."""
    store = ChromaStore(persist_directory=chroma_test_dir)

    chunks = [
        "def authenticate_user(username, password): pass",
        "def query_database(sql): pass",
    ]
    embeddings = [
        [0.1] * 3072,
        [0.9] * 3072,
    ]
    metadatas = [
        {"repo_name": "test/repo", "file_path": "auth.py", "language": "python"},
        {"repo_name": "test/repo", "file_path": "db.py", "language": "python"},
    ]

    # 1. Add chunks
    store.add_code_chunks(
        file_path="auth.py",
        chunks=[chunks[0]],
        embeddings=[embeddings[0]],
        metadata=[metadatas[0]],
    )
    store.add_code_chunks(
        file_path="db.py",
        chunks=[chunks[1]],
        embeddings=[embeddings[1]],
        metadata=[metadatas[1]],
    )

    # 2. Search similar code
    query_vector = [0.1] * 3072
    results = store.search_similar_code(query_vector, limit=2)
    assert len(results) > 0

    # 3. Search repository filtered
    repo_results = store.search_repository(
        "test/repo", query_embedding=query_vector, limit=1
    )
    assert len(repo_results) == 1
    assert repo_results[0]["metadata"]["repo_name"] == "test/repo"
    assert repo_results[0]["metadata"]["file_path"] == "auth.py"

    # 4. Delete repository
    store.delete_repository("test/repo")
    repo_results_after = store.search_repository(
        "test/repo", query_embedding=query_vector, limit=1
    )
    assert len(repo_results_after) == 0

    # 5. Clear database
    store.clear_database()


from unittest.mock import patch


def _repository_chunk(path: str, content: str) -> dict:
    return {"path": path, "content": content, "chunk_id": 0, "language": "python"}


def test_atomic_rebuild_preserves_active_revision_on_failure(chroma_test_dir) -> None:
    store = ChromaStore(persist_directory=chroma_test_dir)
    old_chunks = [_repository_chunk("old.py", "old implementation")]
    store.index_repository("owner/repo", old_chunks, [[0.1, 0.2, 0.3]])

    with patch.object(store.collection, "add", side_effect=RuntimeError("staging failed")):
        with pytest.raises(RuntimeError, match="staging failed"):
            store.index_repository(
                "owner/repo",
                [_repository_chunk("new.py", "new implementation")],
                [[0.1, 0.2, 0.3]],
            )

    active_paths = store.get_repository_file_paths("owner/repo")
    assert active_paths == ["old.py"]


def test_atomic_rebuild_publishes_complete_new_revision(chroma_test_dir) -> None:
    store = ChromaStore(persist_directory=chroma_test_dir)
    store.index_repository("owner/repo", [_repository_chunk("old.py", "old")], [[0.1, 0.2, 0.3]])
    store.index_repository("owner/repo", [_repository_chunk("new.py", "new")], [[0.1, 0.2, 0.3]])

    assert store.get_repository_file_paths("owner/repo") == ["new.py"]
    assert store.get_file_chunks("owner/repo", "old.py").get("ids", []) == []
    assert store.get_file_chunks("owner/repo", "new.py").get("ids", [])


def test_rename_vector_update_removes_old_path_and_indexes_new_path(chroma_test_dir) -> None:
    store = ChromaStore(persist_directory=chroma_test_dir)
    store.index_repository(
        "owner/repo", [_repository_chunk("old_name.py", "same content")], [[0.1, 0.2, 0.3]]
    )

    store.delete_files("owner/repo", ["old_name.py"])
    store.add_code_chunks_bulk(
        ["owner_repo_new_name_py_0"],
        ["same content"],
        [[0.1, 0.2, 0.3]],
        [{"repo_name": "owner/repo", "file_path": "new_name.py", "chunk_id": 0, "language": "python"}],
    )

    assert store.get_file_chunks("owner/repo", "old_name.py").get("ids", []) == []
    assert store.get_repository_file_paths("owner/repo") == ["new_name.py"]


def test_atomic_rebuild_keeps_old_revision_queryable_while_staging(chroma_test_dir, monkeypatch) -> None:
    store = ChromaStore(persist_directory=chroma_test_dir)
    store.index_repository("owner/repo", [_repository_chunk("old.py", "old")], [[0.1, 0.2, 0.3]])
    original_add = store._add_in_batches
    observed_paths = []

    def observe_then_stage(*args, **kwargs):
        observed_paths.extend(store.get_repository_file_paths("owner/repo"))
        return original_add(*args, **kwargs)

    monkeypatch.setattr(store, "_add_in_batches", observe_then_stage)
    store.index_repository("owner/repo", [_repository_chunk("new.py", "new")], [[0.1, 0.2, 0.3]])

    assert observed_paths == ["old.py"]
