"""Unit tests for Phase 1 semantic domain models.

Verifies immutability, invariant enforcement, deterministic equality, and absence of external infrastructure dependencies.
"""

from __future__ import annotations

from datetime import datetime, timezone
import pytest

from ria.domain.enums import (
    DeclarationKind,
    DiagnosticSeverity,
    InheritanceKind,
    ReferenceKind,
    ScopeKind,
    Visibility,
)
from ria.domain.identity import CommitSha, ContentHash, RepositoryId
from ria.domain.models.inheritance import InheritanceRelation, OverrideRelation
from ria.domain.models.namespace import Namespace
from ria.domain.models.namespace_id import NamespaceId
from ria.domain.models.parser_identity import ComponentVersion, ParserFingerprint
from ria.domain.models.scope import Scope
from ria.domain.models.scope_id import ScopeId
from ria.domain.models.semantic_identity import SemanticCacheKey, SemanticFingerprint
from ria.domain.models.semantic_result import (
    ResolutionDiagnostic,
    ResolutionMetadata,
    ResolutionResult,
    ResolutionStatistics,
    ResolutionTiming,
)
from ria.domain.models.span import SourcePosition, SourceSpan
from ria.domain.models.symbol import Symbol
from ria.domain.models.symbol_id import SymbolId
from ria.domain.models.symbol_reference import ReferenceTarget, SymbolReference


@pytest.fixture
def sample_span() -> SourceSpan:
    return SourceSpan(
        start=SourcePosition(byte=0, line=1, column=0),
        end=SourcePosition(byte=20, line=1, column=20),
    )


@pytest.fixture
def sample_fingerprint() -> ParserFingerprint:
    return ParserFingerprint(
        parser=ComponentVersion("tree-sitter", "0.21.0"),
        extractor=ComponentVersion("py-extractor", "1.0.0"),
        language=ComponentVersion("python", "3.12"),
    )


class TestSymbolId:
    def test_construction_and_validation(self, sample_span: SourceSpan) -> None:
        sym_id = SymbolId.for_symbol("python", "src/main.py", "greet", sample_span)
        assert sym_id.value.startswith("sym:python:src/main.py:greet:")
        assert str(sym_id) == sym_id.value

        with pytest.raises(ValueError, match="non-empty"):
            SymbolId(value="")

    def test_equality(self, sample_span: SourceSpan) -> None:
        id1 = SymbolId.for_symbol("python", "src/main.py", "greet", sample_span)
        id2 = SymbolId.for_symbol("python", "src/main.py", "greet", sample_span)
        assert id1 == id2
        assert hash(id1) == hash(id2)


class TestScopeId:
    def test_construction_and_validation(self, sample_span: SourceSpan) -> None:
        s_id = ScopeId.for_scope(
            "python", "src/main.py", ScopeKind.FUNCTION, "greet", sample_span
        )
        assert "scope:python:src/main.py:function:greet:" in s_id.value
        root_id = ScopeId.root("python", "src/main.py")
        assert root_id.value == "scope:python:src/main.py:root"

        with pytest.raises(ValueError, match="non-empty"):
            ScopeId(value="")


class TestNamespaceId:
    def test_construction(self) -> None:
        ns_id = NamespaceId.for_namespace("python", "src/pkg", "src.pkg")
        assert ns_id.value == "ns:python:src/pkg:src.pkg"

        with pytest.raises(ValueError, match="non-empty"):
            NamespaceId(value="")


class TestSymbol:
    def test_symbol_invariants_and_immutability(
        self, sample_span: SourceSpan, sample_fingerprint: ParserFingerprint
    ) -> None:
        sym_id = SymbolId.for_symbol("python", "src/main.py", "greet", sample_span)
        scope_id = ScopeId.root("python", "src/main.py")

        sym = Symbol(
            symbol_id=sym_id,
            name="greet",
            qualified_name="main.greet",
            kind=DeclarationKind.FUNCTION,
            language="python",
            location=sample_span,
            visibility=Visibility.PUBLIC,
            scope_id=scope_id,
            parser_fingerprint=sample_fingerprint,
        )
        assert sym.name == "greet"
        assert sym.kind is DeclarationKind.FUNCTION

        with pytest.raises(ValueError, match="name must be non-empty"):
            Symbol(
                symbol_id=sym_id,
                name="",
                qualified_name="main.greet",
                kind=DeclarationKind.FUNCTION,
                language="python",
                location=sample_span,
                visibility=Visibility.PUBLIC,
                scope_id=scope_id,
                parser_fingerprint=sample_fingerprint,
            )


class TestScope:
    def test_scope_invariants(self, sample_span: SourceSpan) -> None:
        root_id = ScopeId.root("python", "src/main.py")
        scope = Scope(
            scope_id=root_id,
            kind=ScopeKind.MODULE,
            span=sample_span,
            language="python",
        )
        assert scope.is_root
        assert scope.kind is ScopeKind.MODULE

        child_id = ScopeId.for_scope(
            "python", "src/main.py", ScopeKind.FUNCTION, "fn", sample_span
        )
        child_scope = Scope(
            scope_id=child_id,
            kind=ScopeKind.FUNCTION,
            span=sample_span,
            language="python",
            name="fn",
            parent_id=root_id,
        )
        assert not child_scope.is_root
        assert child_scope.parent_id == root_id


class TestNamespace:
    def test_namespace_model(self) -> None:
        ns_id = NamespaceId.for_namespace("python", "src/pkg", "src.pkg")
        ns = Namespace(
            namespace_id=ns_id,
            name="pkg",
            path="src/pkg",
            language="python",
        )
        assert ns.name == "pkg"
        assert ns.path == "src/pkg"


class TestSymbolReference:
    def test_reference_target_and_symbol_reference(
        self, sample_span: SourceSpan
    ) -> None:
        scope_id = ScopeId.root("python", "src/main.py")
        target = ReferenceTarget(target_name="calculate")
        assert not target.is_resolved

        sym_id = SymbolId.for_symbol("python", "src/utils.py", "calculate", sample_span)
        resolved_target = target.with_resolved(sym_id)
        assert resolved_target.is_resolved
        assert resolved_target.target_symbol_id == sym_id

        ref = SymbolReference(
            span=sample_span,
            scope_id=scope_id,
            target=resolved_target,
            kind=ReferenceKind.CALL,
            location_file_path="src/main.py",
        )
        assert ref.kind is ReferenceKind.CALL
        assert ref.target.is_resolved


class TestInheritanceAndOverride:
    def test_inheritance_relation(self, sample_span: SourceSpan) -> None:
        child_id = SymbolId.for_symbol("python", "src/models.py", "Dog", sample_span)
        parent_id = SymbolId.for_symbol(
            "python", "src/models.py", "Animal", sample_span
        )

        rel = InheritanceRelation(
            child_symbol_id=child_id,
            parent_name="Animal",
            kind=InheritanceKind.EXTENDS,
            span=sample_span,
        )
        assert not rel.is_resolved

        resolved_rel = rel.with_resolved_parent(parent_id)
        assert resolved_rel.is_resolved
        assert resolved_rel.parent_symbol_id == parent_id

    def test_override_relation(self, sample_span: SourceSpan) -> None:
        child_fn = SymbolId.for_symbol(
            "python", "src/models.py", "Dog.speak", sample_span
        )
        parent_fn = SymbolId.for_symbol(
            "python", "src/models.py", "Animal.speak", sample_span
        )

        ovr = OverrideRelation(
            overriding_symbol_id=child_fn,
            overridden_symbol_id=parent_fn,
            overridden_name="speak",
            span=sample_span,
        )
        assert ovr.overridden_name == "speak"


class TestSemanticIdentity:
    def test_semantic_fingerprint_and_cache_key(
        self, sample_fingerprint: ParserFingerprint
    ) -> None:
        sem_fp = SemanticFingerprint(
            resolver_name="python-resolver",
            resolver_version="1.0.0",
            parser_fingerprint=sample_fingerprint,
            language="python",
        )
        assert len(sem_fp.digest()) == 64
        assert "sem:python:python-resolver@1.0.0" in sem_fp.token()

        ch = ContentHash.of_bytes(b"content")
        key = SemanticCacheKey(
            content_hash=ch,
            language="python",
            fingerprint=sem_fp,
        )
        assert key.reuse_key == f"{ch.value}|python"
        assert len(key.digest()) == 64


class TestSemanticResultAndStats:
    def test_resolution_statistics_validation(self) -> None:
        stats = ResolutionStatistics(
            symbols_total=10,
            scopes_total=3,
            references_total=5,
            references_resolved=4,
        )
        assert stats.resolution_pct == 80.0

        with pytest.raises(ValueError, match="cannot exceed"):
            ResolutionStatistics(
                references_total=5,
                references_resolved=10,
            )

    def test_resolution_result(self) -> None:
        diag = ResolutionDiagnostic(
            severity=DiagnosticSeverity.WARNING,
            message="Unresolved import 'foo'",
            code="UNRESOLVED_IMPORT",
        )
        timing = ResolutionTiming(scope_seconds=0.01, total_seconds=0.05)
        meta = ResolutionMetadata(
            repository_id=RepositoryId("repo-1"),
            commit_sha=CommitSha("a" * 40),
            language="python",
            resolved_at=datetime.now(timezone.utc),
        )

        assert meta.language == "python"
        res = ResolutionResult(
            diagnostics=(diag,),
            timing=timing,
        )
        assert len(res.diagnostics) == 1
        assert res.timing.total_seconds == 0.05
