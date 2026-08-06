"""Unit tests for CrossFileResolverService (Phase 7)."""

from __future__ import annotations

import pytest

from ria.application.cross_file_resolver import CrossFileResolverService
from ria.domain.enums import DeclarationKind, ReferenceKind, Visibility
from ria.domain.models.parser_identity import ComponentVersion, ParserFingerprint
from ria.domain.models.scope_id import ScopeId
from ria.domain.models.span import SourcePosition, SourceSpan
from ria.domain.models.symbol import Symbol
from ria.domain.models.symbol_id import SymbolId
from ria.domain.models.symbol_reference import ReferenceTarget, SymbolReference


@pytest.fixture
def sample_fingerprint() -> ParserFingerprint:
    return ParserFingerprint(
        parser=ComponentVersion("tree-sitter", "0.21.0"),
        extractor=ComponentVersion("py-extractor", "1.0.0"),
        language=ComponentVersion("python", "3.12"),
    )


def test_cross_file_resolution(sample_fingerprint: ParserFingerprint) -> None:
    pos = SourcePosition(byte=0, line=0, column=0)
    span = SourceSpan(start=pos, end=pos)

    # Symbol in File B
    sym_b_id = SymbolId.for_symbol("python", "src/file_b.py", "export_fn", span)
    sym_b = Symbol(
        symbol_id=sym_b_id,
        name="export_fn",
        qualified_name="file_b.export_fn",
        kind=DeclarationKind.FUNCTION,
        language="python",
        location=span,
        visibility=Visibility.PUBLIC,
        scope_id=ScopeId.root("python", "src/file_b.py"),
        parser_fingerprint=sample_fingerprint,
    )

    # Unresolved reference in File A
    unresolved_target = ReferenceTarget(target_name="export_fn", is_resolved=False)
    ref_a = SymbolReference(
        span=span,
        scope_id=ScopeId.root("python", "src/file_a.py"),
        target=unresolved_target,
        kind=ReferenceKind.READ,
        location_file_path="src/file_a.py",
    )

    resolver = CrossFileResolverService()
    resolved_map = resolver.resolve_cross_file(
        file_references={"src/file_a.py": (ref_a,)},
        all_symbols=(sym_b,),
    )

    assert "src/file_a.py" in resolved_map
    resolved_refs = resolved_map["src/file_a.py"]
    assert len(resolved_refs) == 1
    assert resolved_refs[0].target.is_resolved
    assert resolved_refs[0].target.target_symbol_id == sym_b_id
