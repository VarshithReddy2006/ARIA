"""Unit tests for ScopeBuilder application service (Phase 3)."""

from __future__ import annotations

import pytest

from ria.application.scope_builder import ScopeBuilder
from ria.domain.enums import ScopeKind
from ria.domain.identity import CommitSha, ContentHash, RepositoryId
from ria.domain.models.file_unit import FileUnit
from ria.domain.models.span import SourcePosition, SourceSpan
from ria.domain.models.syntax_facts import ExtractedSyntax
from ria.domain.models.syntax_tree import SyntaxNode, SyntaxTree


@pytest.fixture
def sample_tree() -> SyntaxTree:
    pos_root_start = SourcePosition(byte=0, line=1, column=0)
    pos_root_end = SourcePosition(byte=200, line=10, column=0)
    root_span = SourceSpan(start=pos_root_start, end=pos_root_end)

    pos_class_start = SourcePosition(byte=10, line=2, column=0)
    pos_class_end = SourcePosition(byte=150, line=8, column=0)
    class_span = SourceSpan(start=pos_class_start, end=pos_class_end)

    pos_method_start = SourcePosition(byte=30, line=3, column=4)
    pos_method_end = SourcePosition(byte=100, line=6, column=4)
    method_span = SourceSpan(start=pos_method_start, end=pos_method_end)

    name_node = SyntaxNode(
        kind="identifier",
        span=SourceSpan(start=pos_class_start, end=pos_class_start),
        field_name="App",
    )
    method_node = SyntaxNode(kind="function_definition", span=method_span)
    class_node = SyntaxNode(
        kind="class_definition", span=class_span, children=(name_node, method_node)
    )

    root_node = SyntaxNode(kind="module", span=root_span, children=(class_node,))
    return SyntaxTree(
        language="python",
        root=root_node,
        content_hash=ContentHash.of_bytes(b"code"),
        source_bytes=200,
    )


def test_build_root_scope() -> None:
    builder = ScopeBuilder()
    unit = FileUnit(
        repository_id=RepositoryId("repo1"),
        commit_sha=CommitSha("a" * 40),
        path="src/app.py",
        content_hash=ContentHash.of_bytes(b"code"),
        blob_sha="blob1",
        language="python",
    )
    root_scope = builder.build_root_scope(unit)
    assert root_scope.is_root
    assert root_scope.kind is ScopeKind.MODULE
    assert root_scope.name == "src/app.py"


def test_build_scopes(sample_tree: SyntaxTree) -> None:
    builder = ScopeBuilder()
    extracted = ExtractedSyntax()
    scopes = builder.build_scopes(sample_tree, extracted)

    assert len(scopes) == 3
    root_scope = scopes[0]
    assert root_scope.is_root
    assert root_scope.kind is ScopeKind.MODULE

    class_scope = scopes[1]
    assert class_scope.kind is ScopeKind.CLASS
    assert class_scope.parent_id == root_scope.scope_id

    method_scope = scopes[2]
    assert method_scope.kind is ScopeKind.METHOD
    assert method_scope.parent_id == class_scope.scope_id
