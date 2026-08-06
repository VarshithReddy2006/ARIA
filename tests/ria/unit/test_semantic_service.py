"""Unit tests for SemanticResolutionService (Phases 11 & 14)."""

from __future__ import annotations

import pytest

from ria.application.semantic_service import SemanticResolutionService
from ria.domain.enums import DeclarationKind, Visibility
from ria.domain.identity import CommitSha, ContentHash, RepositoryId
from ria.domain.models.declaration import SyntaxDeclaration
from ria.domain.models.file_unit import FileUnit
from ria.domain.models.parse_result import ParseResult
from ria.domain.models.parser_identity import ComponentVersion, ParserFingerprint
from ria.domain.models.span import SourcePosition, SourceSpan
from ria.domain.models.syntax_facts import ExtractedSyntax
from ria.domain.models.syntax_tree import SyntaxNode, SyntaxTree


@pytest.fixture
def sample_fingerprint() -> ParserFingerprint:
    return ParserFingerprint(
        parser=ComponentVersion("tree-sitter", "0.21.0"),
        extractor=ComponentVersion("py-extractor", "1.0.0"),
        language=ComponentVersion("python", "3.12"),
    )


def test_resolve_unit(sample_fingerprint: ParserFingerprint) -> None:
    unit = FileUnit(
        repository_id=RepositoryId("repo1"),
        commit_sha=CommitSha("a" * 40),
        path="src/main.py",
        content_hash=ContentHash.of_bytes(b"def greet(): pass"),
        blob_sha="blob1",
        language="python",
    )
    pos = SourcePosition(byte=0, line=0, column=0)
    span = SourceSpan(start=pos, end=pos)

    node = SyntaxNode(kind="module", span=span)
    tree = SyntaxTree(
        language="python", root=node, content_hash=unit.content_hash, source_bytes=20
    )
    decl = SyntaxDeclaration(
        kind=DeclarationKind.FUNCTION,
        name="greet",
        span=span,
        name_span=span,
        node_kind="function_definition",
        visibility=Visibility.PUBLIC,
    )
    parse_result = ParseResult(
        reuse_key=unit.reuse_key,
        language="python",
        fingerprint=sample_fingerprint,
        tree=tree,
        extracted=ExtractedSyntax(declarations=(decl,)),
    )

    service = SemanticResolutionService()
    result = service.resolve_unit(unit, parse_result)

    assert len(result.symbols) == 1
    assert result.symbols[0].name == "greet"
    assert len(result.scopes) >= 1
    assert not result.from_cache
