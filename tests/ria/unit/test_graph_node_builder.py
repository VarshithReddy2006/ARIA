"""Unit tests for NodeBuilderService (Phase 3)."""

from __future__ import annotations

import pytest

from ria.application.graph_node_builder import NodeBuilderService
from ria.domain.enums import DeclarationKind, NodeKind, Visibility
from ria.domain.identity import CommitSha, ContentHash, RepositoryId
from ria.domain.models.file_unit import FileUnit
from ria.domain.models.parser_identity import ComponentVersion, ParserFingerprint
from ria.domain.models.scope_id import ScopeId
from ria.domain.models.span import SourcePosition, SourceSpan
from ria.domain.models.symbol import Symbol
from ria.domain.models.symbol_id import SymbolId


@pytest.fixture
def sample_fingerprint() -> ParserFingerprint:
    return ParserFingerprint(
        parser=ComponentVersion("tree-sitter", "0.21.0"),
        extractor=ComponentVersion("py-extractor", "1.0.0"),
        language=ComponentVersion("python", "3.12"),
    )


def test_build_repository_and_commit_nodes() -> None:
    svc = NodeBuilderService()
    repo_id = RepositoryId("my-repo")
    commit_sha = CommitSha("a" * 40)

    repo_node = svc.build_repository_node(repo_id)
    assert repo_node.kind is NodeKind.REPOSITORY
    assert repo_node.name == "my-repo"

    commit_node = svc.build_commit_node(repo_id, commit_sha)
    assert commit_node.kind is NodeKind.COMMIT
    assert commit_node.name == ("a" * 40)[:7]


def test_build_file_and_symbol_nodes(sample_fingerprint: ParserFingerprint) -> None:
    svc = NodeBuilderService()
    repo_id = RepositoryId("my-repo")

    unit = FileUnit(
        repository_id=repo_id,
        commit_sha=CommitSha("a" * 40),
        path="src/utils.py",
        content_hash=ContentHash.of_bytes(b"code"),
        blob_sha="b1",
        language="python",
    )
    file_node = svc.build_file_node(repo_id, unit)
    assert file_node.kind is NodeKind.MODULE
    assert file_node.location_path == "src/utils.py"

    pos = SourcePosition(0, 0, 0)
    span = SourceSpan(pos, pos)
    sym_id = SymbolId.for_symbol("python", "src/utils.py", "helper", span)
    sym = Symbol(
        symbol_id=sym_id,
        name="helper",
        qualified_name="helper",
        kind=DeclarationKind.FUNCTION,
        language="python",
        location=span,
        visibility=Visibility.PUBLIC,
        scope_id=ScopeId.root("python", "src/utils.py"),
        parser_fingerprint=sample_fingerprint,
    )

    nodes = svc.build_symbol_nodes(repo_id, (sym,))
    assert len(nodes) == 1
    assert nodes[0].kind is NodeKind.FUNCTION
    assert nodes[0].name == "helper"
