"""Unit tests for InheritanceResolverService (Phase 8)."""

from __future__ import annotations

import pytest

from ria.application.inheritance_resolver import InheritanceResolverService
from ria.domain.enums import DeclarationKind, InheritanceKind, Visibility
from ria.domain.models.declaration import SyntaxDeclaration
from ria.domain.models.parser_identity import ComponentVersion, ParserFingerprint
from ria.domain.models.scope_id import ScopeId
from ria.domain.models.span import SourcePosition, SourceSpan
from ria.domain.models.symbol import Symbol
from ria.domain.models.symbol_id import SymbolId
from ria.domain.models.syntax_facts import ExtractedSyntax


@pytest.fixture
def sample_fingerprint() -> ParserFingerprint:
    return ParserFingerprint(
        parser=ComponentVersion("tree-sitter", "0.21.0"),
        extractor=ComponentVersion("py-extractor", "1.0.0"),
        language=ComponentVersion("python", "3.12"),
    )


def test_resolve_inheritance_and_overrides(
    sample_fingerprint: ParserFingerprint,
) -> None:
    pos = SourcePosition(byte=0, line=0, column=0)
    span = SourceSpan(start=pos, end=pos)

    # Parent Animal
    animal_id = SymbolId.for_symbol("python", "src/animals.py", "Animal", span)
    animal_sym = Symbol(
        symbol_id=animal_id,
        name="Animal",
        qualified_name="Animal",
        kind=DeclarationKind.CLASS,
        language="python",
        location=span,
        visibility=Visibility.PUBLIC,
        scope_id=ScopeId.root("python", "src/animals.py"),
        parser_fingerprint=sample_fingerprint,
    )

    animal_speak_id = SymbolId.for_symbol(
        "python", "src/animals.py", "Animal.speak", span
    )
    animal_speak = Symbol(
        symbol_id=animal_speak_id,
        name="speak",
        qualified_name="Animal.speak",
        kind=DeclarationKind.METHOD,
        language="python",
        location=span,
        visibility=Visibility.PUBLIC,
        scope_id=ScopeId.root("python", "src/animals.py"),
        parser_fingerprint=sample_fingerprint,
        signature_text="def speak(self)",
    )
    object.__setattr__(animal_speak, "container_path", ("Animal",))

    # Child Dog extending Animal
    dog_id = SymbolId.for_symbol("python", "src/animals.py", "Dog", span)
    dog_sym = Symbol(
        symbol_id=dog_id,
        name="Dog",
        qualified_name="Dog",
        kind=DeclarationKind.CLASS,
        language="python",
        location=span,
        visibility=Visibility.PUBLIC,
        scope_id=ScopeId.root("python", "src/animals.py"),
        parser_fingerprint=sample_fingerprint,
    )

    dog_speak_id = SymbolId.for_symbol("python", "src/animals.py", "Dog.speak", span)
    dog_speak = Symbol(
        symbol_id=dog_speak_id,
        name="speak",
        qualified_name="Dog.speak",
        kind=DeclarationKind.METHOD,
        language="python",
        location=span,
        visibility=Visibility.PUBLIC,
        scope_id=ScopeId.root("python", "src/animals.py"),
        parser_fingerprint=sample_fingerprint,
        signature_text="def speak(self)",
    )
    object.__setattr__(dog_speak, "container_path", ("Dog",))

    decl = SyntaxDeclaration(
        kind=DeclarationKind.CLASS,
        name="Dog",
        span=span,
        name_span=span,
        node_kind="class_definition",
        modifiers=("Animal",),
    )
    extracted = ExtractedSyntax(declarations=(decl,))

    resolver = InheritanceResolverService()
    inh_rels, ovr_rels = resolver.resolve_inheritance(
        extracted, (animal_sym, animal_speak, dog_sym, dog_speak)
    )

    assert len(inh_rels) == 1
    assert inh_rels[0].child_symbol_id == dog_id
    assert inh_rels[0].parent_name == "Animal"
    assert inh_rels[0].parent_symbol_id == animal_id
    assert inh_rels[0].kind is InheritanceKind.EXTENDS

    assert len(ovr_rels) == 1
    assert ovr_rels[0].overriding_symbol_id == dog_speak_id
    assert ovr_rels[0].overridden_symbol_id == animal_speak_id
    assert ovr_rels[0].overridden_name == "speak"
