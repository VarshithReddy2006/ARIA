"""Unit tests for GraphRegistry and GraphBuilderService (Phases 10 & 11)."""

from __future__ import annotations

import pytest

from ria.application.graph_registry import GraphRegistry
from ria.application.graph_service import GraphBuilderService
from ria.domain.enums import DeclarationKind, EdgeKind, NodeKind, Visibility
from ria.domain.identity import CommitSha, ContentHash, RepositoryId
from ria.domain.models.file_unit import FileUnit
from ria.domain.models.parser_identity import ComponentVersion, ParserFingerprint
from ria.domain.models.scope import Scope
from ria.domain.models.scope_id import ScopeId
from ria.domain.models.semantic_result import ResolutionResult
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


def test_graph_registry() -> None:
    reg = GraphRegistry()
    assert NodeKind.FUNCTION in reg.supported_node_kinds()
    assert EdgeKind.CALLS in reg.supported_edge_kinds()
    assert reg.builder_version().name == "default-graph-builder"


def test_graph_builder_service(sample_fingerprint: ParserFingerprint) -> None:
    repo_id = RepositoryId("repo1")
    commit_sha = CommitSha("a" * 40)

    unit = FileUnit(
        repository_id=repo_id,
        commit_sha=commit_sha,
        path="src/app.py",
        content_hash=ContentHash.of_bytes(b"def main(): pass"),
        blob_sha="blob1",
        language="python",
    )

    pos = SourcePosition(0, 0, 0)
    span = SourceSpan(pos, pos)
    sym_id = SymbolId.for_symbol("python", "src/app.py", "main", span)
    scope_id = ScopeId.root("python", "src/app.py")

    sym = Symbol(
        symbol_id=sym_id,
        name="main",
        qualified_name="main",
        kind=DeclarationKind.FUNCTION,
        language="python",
        location=span,
        visibility=Visibility.PUBLIC,
        scope_id=scope_id,
        parser_fingerprint=sample_fingerprint,
    )
    scope = Scope(
        scope_id=scope_id,
        kind=DeclarationKind.FUNCTION,
        span=span,
        language="python",
        name="src/app.py",
    )

    resolution = ResolutionResult(symbols=(sym,), scopes=(scope,))

    svc = GraphBuilderService()
    snapshot = svc.build_graph(repo_id, commit_sha, (unit,), (resolution,))

    assert snapshot.repository_id == repo_id
    assert snapshot.commit_sha == commit_sha
    assert (
        len(snapshot.graph.nodes) >= 3
    )  # Repo node, Commit node, File node, Symbol node, Scope node
    assert snapshot.statistics.nodes_total == len(snapshot.graph.nodes)
