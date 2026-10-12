"""Deterministic file lookup must distinguish paths that differ only by case."""

import pytest

from services.chat.retrieval import detect_deterministic_retrieval


class _Store:
    def __init__(self, paths):
        self._paths = paths

    def get_repository_file_paths(self, repo_name):
        return list(self._paths)

    def get(self, include=None, where=None):
        return {"metadatas": [{"file_path": p} for p in self._paths]}


@pytest.mark.parametrize(
    "paths",
    [
        ["src/getUser.py", "src/getuser.py"],
        ["src/getuser.py", "src/getUser.py"],
    ],
)
@pytest.mark.parametrize("target", ["src/getUser.py", "src/getuser.py"])
def test_full_path_differing_only_by_case_resolves_exactly(paths, target):
    res = detect_deterministic_retrieval(
        f"Explain `{target}`", "o/r", _Store(paths), None
    )
    assert res is not None
    assert res["matched_file"] == target


@pytest.mark.parametrize("target", ["getUser.py", "getuser.py"])
def test_filename_differing_only_by_case_resolves_exactly(target):
    paths = ["src/getuser.py", "src/getUser.py"]
    res = detect_deterministic_retrieval(
        f"Explain `{target}`", "o/r", _Store(paths), None
    )
    assert res["matched_file"] == "src/" + target


def test_case_insensitive_fallback_still_works_without_exact_match():
    paths = ["src/GetUser.py"]
    res = detect_deterministic_retrieval(
        "Explain `src/getuser.py`", "o/r", _Store(paths), None
    )
    assert res["matched_file"] == "src/GetUser.py"
