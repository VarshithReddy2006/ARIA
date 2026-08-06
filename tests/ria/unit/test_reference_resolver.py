"""Unit tests for ReferenceResolverService (Phase 6)."""

from __future__ import annotations

import pytest

from ria.application.reference_resolver import ReferenceResolverService
from ria.application.scope_builder import ScopeBuilder
from ria.application.symbol_extractor import SymbolExtractorService
from ria.domain.enums import DeclarationKind, ReferenceKind, Visibility
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
        extractor=ComponentVersion("py-extractor", "1.0.0"),
        language=ComponentVersion("python", "3.12"),
    )


def test_resolve_references(sample_fingerprint: ParserFingerprint) -> None:
    pos1 = SourcePosition(byte=0, line=0, column=0)
    pos2 = SourcePosition(byte=100, line=5, column=0)
    span = SourceSpan(start=pos1, end=pos2)

    id_node = SyntaxNode(kind="identifier", span=span, field_name="compute")
    root_node = SyntaxNode(kind="module", span=span, children=(id_node,))
    tree = SyntaxTree(
        language="python",
        root=root_node,
        content_hash=ContentHash.of_bytes(b"code"),
        source_bytes=100,
    )

    decl = SyntaxDeclaration(
        kind=DeclarationKind.FUNCTION,
        name="compute",
        span=span,
        name_span=span,
        node_kind="function_definition",
        visibility=Visibility.PUBLIC,
    )
    extracted = ExtractedSyntax(declarations=(decl,))

    scopes = ScopeBuilder().build_scopes(tree, extracted, file_path="src/math.py")
    symbols = SymbolExtractorService().extract_symbols(
        tree, extracted, scopes, sample_fingerprint
    )

    ref_service = ReferenceResolverService()
    refs = ref_service.resolve_references(tree, extracted, scopes, symbols)

    assert len(refs) == 1
    ref = refs[0]
    assert ref.target.target_name == "compute"
    assert ref.target.is_resolved
    assert ref.target.target_symbol_id == symbols[0].symbol_id
    assert ref.kind is ReferenceKind.READ
