"""C2 Semantic Resolution Domain Package."""

from ria.domain.resolution.entities import ResolvedFactSet, SemanticSymbol
from ria.domain.resolution.exceptions import (
    InvalidMonikerError,
    InvalidQualifiedNameError,
    ResolutionDomainException,
    ScopeResolutionError,
)
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

__all__ = [
    "SymbolKind",
    "Visibility",
    "RelationKind",
    "SymbolMoniker",
    "QualifiedName",
    "Documentation",
    "TypeAnnotation",
    "SymbolModifiers",
    "SemanticDefinition",
    "SemanticReference",
    "CallRelation",
    "ImportRelation",
    "InheritanceRelation",
    "SemanticRelation",
    "SemanticSymbol",
    "ResolvedFactSet",
    "ResolutionDomainException",
    "InvalidMonikerError",
    "InvalidQualifiedNameError",
    "ScopeResolutionError",
]
