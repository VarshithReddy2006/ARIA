"""Unit tests for ImportResolverService (Phase 5)."""

from __future__ import annotations

import pytest

from ria.application.import_resolver import ImportResolverService
from ria.domain.enums import DeclarationKind, ReferenceKind, Visibility
from ria.domain.identity import CommitSha, ContentHash, RepositoryId
from ria.domain.models.file_unit import FileUnit
from ria.domain.models.parser_identity import ComponentVersion, ParserFingerprint
from ria.domain.models.scope_id import ScopeId
from ria.domain.models.span import SourcePosition, SourceSpan
from ria.domain.models.symbol import Symbol
from ria.domain.models.symbol_id import SymbolId
from ria.domain.models.syntax_facts import (
    ExportStatement,
    ExtractedSyntax,
    ImportedName,
    ImportStatement,
)


@pytest.fixture
def sample_fingerprint() -> ParserFingerprint:
    return ParserFingerprint(
        parser=ComponentVersion("tree-sitter", "0.21.0"),
        extractor=ComponentVersion("py-extractor", "1.0.0"),
        language=ComponentVersion("python", "3.12"),
    )


def test_resolve_imports(sample_fingerprint: ParserFingerprint) -> None:
    unit = FileUnit(
        repository_id=RepositoryId("repo1"),
        commit_sha=CommitSha("a" * 40),
        path="src/main.py",
        content_hash=ContentHash.of_bytes(b"import helper"),
        blob_sha="blob1",
        language="python",
    )
    pos = SourcePosition(byte=0, line=0, column=0)
    span = SourceSpan(start=pos, end=pos)

    imp = ImportStatement(
        module_text="utils",
        span=span,
        node_kind="import_statement",
        names=(ImportedName(name="helper"),),
    )
    exp = ExportStatement(
        span=span,
        node_kind="export_statement",
        names=(ImportedName(name="helper"),),
    )
    extracted = ExtractedSyntax(imports=(imp,), exports=(exp,))

    target_sym_id = SymbolId.for_symbol("python", "src/utils.py", "helper", span)
    target_sym = Symbol(
        symbol_id=target_sym_id,
        name="helper",
        qualified_name="utils.helper",
        kind=DeclarationKind.FUNCTION,
        language="python",
        location=span,
        visibility=Visibility.PUBLIC,
        scope_id=ScopeId.root("python", "src/utils.py"),
        parser_fingerprint=sample_fingerprint,
    )

    service = ImportResolverService()
    refs = service.resolve_imports(unit, extracted, available_symbols=(target_sym,))

    assert len(refs) == 2
    imp_ref = refs[0]
    assert imp_ref.kind is ReferenceKind.IMPORT
    assert imp_ref.target.is_resolved
    assert imp_ref.target.target_symbol_id == target_sym_id

    exp_ref = refs[1]
    assert exp_ref.kind is ReferenceKind.EXPORT
    assert exp_ref.target.is_resolved
