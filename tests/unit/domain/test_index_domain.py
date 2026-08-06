"""Unit tests for C1 Index Core domain invariants."""

import pytest
from ria.domain.common.value_objects import Timestamp, UUIDv4
from ria.domain.index import (
    ASTNode,
    ASTUnit,
    ContentHash,
    FilePath,
    FileUnit,
    IndexBatch,
    Language,
    ParseUnit,
)
from ria.domain.sync import CommitReference, RepositoryIdentity


def test_language_from_extension() -> None:
    assert Language.from_extension(".py") == Language.PYTHON
    assert Language.from_extension("ts") == Language.TYPESCRIPT
    assert Language.from_extension("js") == Language.JAVASCRIPT
    assert Language.from_extension("unknown") == Language.UNKNOWN


def test_file_path_invariants() -> None:
    fp = FilePath(relative_path="src/utils.py")
    assert fp.extension == ".py"

    with pytest.raises(ValueError, match="POSIX forward slash"):
        FilePath(relative_path="src\\utils.py")

    with pytest.raises(ValueError, match="must be relative"):
        FilePath(relative_path="/src/utils.py")


def test_content_hash_validation() -> None:
    valid_hash = "c" * 64
    ch = ContentHash(sha256_hex=valid_hash)
    assert ch.sha256_hex == valid_hash

    with pytest.raises(ValueError, match="64-character hex"):
        ContentHash(sha256_hex="short")


def test_index_batch_immutability() -> None:
    fp = FilePath(relative_path="main.py")
    ch = ContentHash(sha256_hex="f" * 64)
    file_unit = FileUnit(path=fp, language=Language.PYTHON, content_hash=ch, size_bytes=100)

    ast_node = ASTNode(type="module", start_line=1, start_col=0, end_line=10, end_col=0)
    ast_unit = ASTUnit(path=fp, language=Language.PYTHON, root_node=ast_node, total_nodes=1)
    parse_unit = ParseUnit(file_unit=file_unit, ast_unit=ast_unit, parse_duration_ms=1.5)

    repo_id = RepositoryIdentity(repo_id=UUIDv4.generate(), remote_url="https://github.com/a/b.git", name="b")
    commit = CommitReference(sha="e" * 40, committed_at=Timestamp.now())

    batch = IndexBatch(
        batch_id=UUIDv4.generate(),
        repo_id=repo_id,
        commit=commit,
        parse_units=(parse_unit,),
        created_at=Timestamp.now(),
    )
    assert len(batch.parse_units) == 1
    assert batch.parse_units[0].file_unit.path.relative_path == "main.py"
