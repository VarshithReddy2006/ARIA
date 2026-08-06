"""Unit tests for C2 Resolution Engine domain models, language resolvers, and engine."""

from pathlib import Path

import pytest
from ria.domain.common.value_objects import Timestamp, UUIDv4
from ria.domain.index.units import ASTUnit, FileUnit, ParseUnit
from ria.domain.index.value_objects import ASTNode, ContentHash, FilePath, Language, Location
from ria.domain.resolution import (
    CallRelation,
    ImportRelation,
    InheritanceRelation,
    InvalidMonikerError,
    InvalidQualifiedNameError,
    QualifiedName,
    RelationKind,
    ResolvedFactSet,
    SemanticRelation,
    SymbolKind,
    SymbolMoniker,
    Visibility,
)
from ria.domain.sync import CommitReference, RepositoryIdentity
from ria.resolution import (
    JavaScriptLanguageResolver,
    LanguageResolverRegistry,
    PythonLanguageResolver,
    ResolutionContext,
    ResolutionEngine,
    TypeScriptLanguageResolver,
)
from ria.resolution.extractors.relationship_resolver import RelationshipResolver


def test_resolution_domain_value_objects() -> None:
    moniker = SymbolMoniker(value="repo:src/app.py:global:add")
    qname = QualifiedName(dotted_path="src.app.add")

    assert moniker.value == "repo:src/app.py:global:add"
    assert qname.dotted_path == "src.app.add"

    with pytest.raises(InvalidMonikerError):
        SymbolMoniker(value="")

    with pytest.raises(InvalidQualifiedNameError):
        QualifiedName(dotted_path="")


def test_python_language_resolver_extraction() -> None:
    fn_ident = ASTNode(type="identifier", start_line=1, start_col=4, end_line=1, end_col=12, attributes=(("text", "multiply"),))
    fn_node = ASTNode(type="function_definition", start_line=1, start_col=0, end_line=2, end_col=18, children=(fn_ident,))
    cls_ident = ASTNode(type="identifier", start_line=3, start_col=6, end_line=3, end_col=17, attributes=(("text", "Calculator"),))
    cls_node = ASTNode(type="class_definition", start_line=3, start_col=0, end_line=5, end_col=20, children=(cls_ident,))
    imp_node = ASTNode(
        type="import_statement",
        start_line=6,
        start_col=0,
        end_line=6,
        end_col=15,
        children=(ASTNode(type="dotted_name", start_line=6, start_col=7, end_line=6, end_col=15, attributes=(("text", "math"),)),),
    )
    call_ident = ASTNode(type="identifier", start_line=7, start_col=0, end_line=7, end_col=8, attributes=(("text", "multiply"),))
    call_node = ASTNode(type="call", start_line=7, start_col=0, end_line=7, end_col=12, children=(call_ident,))

    root_node = ASTNode(type="module", start_line=1, start_col=0, end_line=7, end_col=12, children=(fn_node, cls_node, imp_node, call_node))

    fp = FilePath(relative_path="math_utils.py")
    ch = ContentHash(sha256_hex="a" * 64)
    file_unit = FileUnit(path=fp, language=Language.PYTHON, content_hash=ch, size_bytes=100)
    ast_unit = ASTUnit(path=fp, language=Language.PYTHON, root_node=root_node, total_nodes=10)
    parse_unit = ParseUnit(file_unit=file_unit, ast_unit=ast_unit, parse_duration_ms=1.0)

    repo_identity = RepositoryIdentity(repo_id=UUIDv4.generate(), remote_url="https://github.com/org/repo.git", name="repo")
    commit = CommitReference(sha="b" * 40, committed_at=Timestamp.now())

    ctx = ResolutionContext(
        repo_id=repo_identity,
        commit=commit,
        current_path=fp,
        language=Language.PYTHON,
    )

    resolver = PythonLanguageResolver()
    assert resolver.can_resolve(Language.PYTHON)
    assert not resolver.can_resolve(Language.TYPESCRIPT)

    fact_set = resolver.resolve_unit(parse_unit, ctx)

    assert len(fact_set.symbols) == 2
    assert len(fact_set.definitions) == 2
    assert len(fact_set.imports) == 1
    assert len(fact_set.calls) == 1
    assert fact_set.total_facts == 6


def test_javascript_language_resolver_extraction() -> None:
    fn_ident = ASTNode(type="identifier", start_line=1, start_col=9, end_line=1, end_col=15, attributes=(("text", "render"),))
    fn_node = ASTNode(type="function_declaration", start_line=1, start_col=0, end_line=3, end_col=1, children=(fn_ident,))
    cls_ident = ASTNode(type="identifier", start_line=4, start_col=6, end_line=4, end_col=15, attributes=(("text", "Component"),))
    cls_node = ASTNode(type="class_declaration", start_line=4, start_col=0, end_line=6, end_col=1, children=(cls_ident,))
    root_node = ASTNode(type="program", start_line=1, start_col=0, end_line=6, end_col=1, children=(fn_node, cls_node))

    fp = FilePath(relative_path="view.js")
    ch = ContentHash(sha256_hex="c" * 64)
    file_unit = FileUnit(path=fp, language=Language.JAVASCRIPT, content_hash=ch, size_bytes=80)
    ast_unit = ASTUnit(path=fp, language=Language.JAVASCRIPT, root_node=root_node, total_nodes=5)
    parse_unit = ParseUnit(file_unit=file_unit, ast_unit=ast_unit, parse_duration_ms=1.0)

    repo_identity = RepositoryIdentity(repo_id=UUIDv4.generate(), remote_url="https://github.com/org/repo.git", name="repo")
    commit = CommitReference(sha="d" * 40, committed_at=Timestamp.now())

    ctx = ResolutionContext(
        repo_id=repo_identity,
        commit=commit,
        current_path=fp,
        language=Language.JAVASCRIPT,
    )

    resolver = JavaScriptLanguageResolver()
    assert resolver.can_resolve(Language.JAVASCRIPT)

    fact_set = resolver.resolve_unit(parse_unit, ctx)

    assert len(fact_set.symbols) == 2
    assert len(fact_set.definitions) == 2


def test_relationship_resolver_methods() -> None:
    rel_res = RelationshipResolver()
    m1 = SymbolMoniker(value="m1")
    m2 = SymbolMoniker(value="m2")
    loc = Location(1, 0, 1, 10)

    call_rel = rel_res.build_call_relation(m1, m2, loc)
    assert call_rel.caller_moniker == m1
    assert call_rel.callee_moniker == m2

    inh_rel = rel_res.build_inheritance_relation(m1, m2, is_interface=True)
    assert inh_rel.is_interface

    gen_rel = rel_res.build_generic_relation(m1, m2, RelationKind.REFERENCES, loc)
    assert gen_rel.kind == RelationKind.REFERENCES


def test_resolution_registry_and_empty_units() -> None:
    registry = LanguageResolverRegistry()
    py_res = PythonLanguageResolver()

    registry.register_resolver(Language.PYTHON, py_res)
    assert registry.get_resolver(Language.PYTHON) == py_res
    assert registry.get_resolver(Language.TYPESCRIPT) is None
    assert Language.PYTHON in registry.supported_languages()

    # Test invalid registration
    with pytest.raises(ValueError, match="declared inability"):
        registry.register_resolver(Language.TYPESCRIPT, py_res)

    # Empty parse unit (no AST)
    fp = FilePath(relative_path="empty.py")
    fu = FileUnit(path=fp, language=Language.PYTHON, content_hash=ContentHash(sha256_hex="e" * 64), size_bytes=0)
    empty_pu = ParseUnit(file_unit=fu, ast_unit=None, parse_duration_ms=0.0)

    repo_identity = RepositoryIdentity(repo_id=UUIDv4.generate(), remote_url="https://github.com/org/repo.git", name="repo")
    commit = CommitReference(sha="f" * 40, committed_at=Timestamp.now())

    res_set = py_res.resolve_unit(empty_pu, ResolutionContext(repo_identity, commit, fp, Language.PYTHON))
    assert res_set.total_facts == 0
