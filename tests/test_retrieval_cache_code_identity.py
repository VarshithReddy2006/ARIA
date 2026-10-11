"""Code spelling must survive retrieval caching, including deterministic reads."""

from unittest.mock import patch

import pytest

from services.chat.retrieval import intelligent_retrieve
from services.chat.retrieval_cache import RetrievalLRUCache, retrieval_cache


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("get_user.py", "getuser.py"),
        ("__init__.py", "init.py"),
        ("_private", "private"),
        ("a * b", "a b"),
        ("~flags", "flags"),
    ],
)
def test_code_spelling_produces_distinct_cache_keys(first, second):
    assert RetrievalLRUCache.build_key(
        "org/repo", "v1", f"explain {first}"
    ) != RetrievalLRUCache.build_key("org/repo", "v1", f"explain {second}")


def test_deterministic_file_read_does_not_reuse_a_different_filename():
    class Store:
        _enable_retrieval_cache = True

        def __init__(self):
            self.reads = []

        def _active_version(self, repo_name):
            return "v1"

        def get_file_chunks(self, repo_name, file_path):
            self.reads.append(file_path)
            return {
                "ids": [file_path],
                "documents": [f"content of {file_path}"],
                "metadatas": [{"file_path": file_path}],
            }

    store = Store()
    retrieval_cache.invalidate_all()
    try:
        with patch(
            "services.chat.retrieval.get_unique_file_paths",
            return_value=["get_user.py", "getuser.py"],
        ):
            for file_path in ["get_user.py", "getuser.py", "getuser.py"]:
                chunks, metrics = intelligent_retrieve(
                    question=f"explain {file_path}",
                    repo_name="org/repo",
                    embedding_service=None,
                    chroma_store=store,
                    deterministic_match={
                        "matched_file": file_path,
                        "confidence": 100,
                        "match_type": "filename",
                        "clarification_needed": False,
                    },
                )
                assert chunks[0]["metadata"]["file_path"] == file_path
            assert metrics["cache_hit"] is True
            assert store.reads == ["get_user.py", "getuser.py"]
    finally:
        retrieval_cache.invalidate_all()
