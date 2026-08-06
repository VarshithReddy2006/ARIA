"""Entities and Aggregate Containers for C2 Semantic Resolution."""

from dataclasses import dataclass, field
from typing import Optional, Tuple

from ria.domain.common.base import ValueObject
from ria.domain.index.value_objects import FilePath, Location
from ria.domain.resolution.value_objects import (
    CallRelation,
    Documentation,
    ImportRelation,
    InheritanceRelation,
    QualifiedName,
    RelationKind,
    SemanticDefinition,
    SemanticReference,
    SemanticRelation,
    SymbolKind,
    SymbolModifiers,
    SymbolMoniker,
    TypeAnnotation,
    Visibility,
)


@dataclass(frozen=True, slots=True)
class SemanticSymbol(ValueObject):
    """Immutable entity representing a fully resolved code symbol."""

    moniker: SymbolMoniker
    name: str
    qualified_name: QualifiedName
    kind: SymbolKind
    visibility: Visibility
    path: FilePath
    location: Location
    doc: Optional[Documentation] = None
    type_annotation: Optional[TypeAnnotation] = None
    modifiers: SymbolModifiers = field(default_factory=SymbolModifiers)

    def _validate_invariants(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("SemanticSymbol name cannot be empty.")


@dataclass(frozen=True, slots=True)
class ResolvedFactSet(ValueObject):
    """Immutable aggregate output container holding all resolved symbols, definitions, references, and relationships."""

    symbols: Tuple[SemanticSymbol, ...] = field(default_factory=tuple)
    definitions: Tuple[SemanticDefinition, ...] = field(default_factory=tuple)
    references: Tuple[SemanticReference, ...] = field(default_factory=tuple)
    calls: Tuple[CallRelation, ...] = field(default_factory=tuple)
    imports: Tuple[ImportRelation, ...] = field(default_factory=tuple)
    inheritance: Tuple[InheritanceRelation, ...] = field(default_factory=tuple)
    relations: Tuple[SemanticRelation, ...] = field(default_factory=tuple)

    @property
    def total_facts(self) -> int:
        """Total number of semantic facts in the set."""
        return (
            len(self.symbols)
            + len(self.definitions)
            + len(self.references)
            + len(self.calls)
            + len(self.imports)
            + len(self.inheritance)
            + len(self.relations)
        )
