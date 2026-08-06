"""Unit tests for SymbolExtractorService (Phase 4)."""

from __future__ import annotations

import pytest

from ria.application.scope_builder import ScopeBuilder
from ria.application.symbol_extractor import SymbolExtractorService
from ria.domain.enums import DeclarationKind, Visibility
from ria.domain.identity import ContentHash
from ria.domain.models.declaration import SyntaxDeclaration
from ria.domain.models.parser_identity import ComponentVersion, ParserFingerprint
from ria.domain.models.span import SourcePosition, SourceSpan
from ria.domain.models.syntax_facts import ExtractedSyntax
from ria.domain.models.syntax_tree import SyntaxNode, SyntaxTree


@pytest.fixture
def sample_fingerprint() -> ParserFingerprint:
    return ParserFingerprint(
        parser=ComponentVersion("tree-sitter", "0.21.0"),
        extractor=ComponentVersion("python-extractor", "1.0.0"),
        language=ComponentVersion("python", "3.12"),
    )


def test_extract_symbols(sample_fingerprint: ParserFingerprint) -> None:
    pos1 = SourcePosition(byte=0, line=0, column=0)
    pos2 = SourcePosition(byte=100, line=5, column=0)
    span = SourceSpan(start=pos1, end=pos2)

    node = SyntaxNode(kind="module", span=span)
    tree = SyntaxTree(
        language="python",
        root=node,
        content_hash=ContentHash.of_bytes(b"code"),
        source_bytes=100,
    )

    decl = SyntaxDeclaration(
        kind=DeclarationKind.FUNCTION,
        name="calculate",
        span=span,
        name_span=span,
        node_kind="function_definition",
        visibility=Visibility.PUBLIC,
    )
    extracted = ExtractedSyntax(declarations=(decl,))

    scope_builder = ScopeBuilder()
    scopes = scope_builder.build_scopes(tree, extracted, file_path="src/calc.py")

    extractor_svc = SymbolExtractorService()
    symbols = extractor_svc.extract_symbols(tree, extracted, scopes, sample_fingerprint)

    assert len(symbols) == 1
    sym = symbols[0]
    assert sym.name == "calculate"
    assert sym.qualified_name == "calculate"
    assert sym.kind is DeclarationKind.FUNCTION
    assert sym.scope_id == scopes[0].scope_id
    assert sym.parser_fingerprint == sample_fingerprint

    lookup = extractor_svc.resolve_symbol_by_id(sym.symbol_id, symbols)
    assert lookup == sym
