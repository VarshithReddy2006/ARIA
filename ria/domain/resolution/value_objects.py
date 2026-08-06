"""Value Objects for C2 Semantic Resolution Engine."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple

from ria.domain.common.base import ValueObject
from ria.domain.index.value_objects import FilePath, Language, Location
from ria.domain.resolution.exceptions import InvalidMonikerError, InvalidQualifiedNameError


class SymbolKind(Enum):
    """Enumeration of semantic code symbol kinds."""

    MODULE = "module"
    CLASS = "class"
    INTERFACE = "interface"
    ENUM = "enum"
    FUNCTION = "function"
    METHOD = "method"
    CONSTRUCTOR = "constructor"
    VARIABLE = "variable"
    PARAMETER = "parameter"
    CONSTANT = "constant"
    IMPORT = "import"
    EXPORT = "export"
    DECORATOR = "decorator"
    NAMESPACE = "namespace"


class Visibility(Enum):
    """Visibility scope of a symbol."""

    PUBLIC = "public"
    PRIVATE = "private"
    PROTECTED = "protected"
    INTERNAL = "internal"


class RelationKind(Enum):
    """Semantic relationship types between code symbols."""

    DEFINES = "DEFINES"
    CALLS = "CALLS"
    IMPORTS = "IMPORTS"
    EXPORTS = "EXPORTS"
    INHERITS_FROM = "INHERITS_FROM"
    OVERRIDES = "OVERRIDES"
    IMPLEMENTS = "IMPLEMENTS"
    REFERENCES = "REFERENCES"


@dataclass(frozen=True, slots=True)
class SymbolMoniker(ValueObject):
    """Immutable, globally unique symbol descriptor string."""

    value: str

    def _validate_invariants(self) -> None:
        if not self.value or not self.value.strip():
            raise InvalidMonikerError("SymbolMoniker value cannot be empty.")


@dataclass(frozen=True, slots=True)
class QualifiedName(ValueObject):
    """Immutable scoped, dotted identifier path of a symbol."""

    dotted_path: str

    def _validate_invariants(self) -> None:
        if not self.dotted_path or not self.dotted_path.strip():
            raise InvalidQualifiedNameError("QualifiedName dotted path cannot be empty.")


@dataclass(frozen=True, slots=True)
class Documentation(ValueObject):
    """Immutable documentation docstring snippet."""

    docstring: str
    summary: str = ""


@dataclass(frozen=True, slots=True)
class TypeAnnotation(ValueObject):
    """Immutable static type annotation descriptor."""

    raw_annotation: str


@dataclass(frozen=True, slots=True)
class SymbolModifiers(ValueObject):
    """Immutable modifier flags for a symbol."""

    is_static: bool = False
    is_async: bool = False
    is_abstract: bool = False
    is_readonly: bool = False
    is_exported: bool = False


@dataclass(frozen=True, slots=True)
class SemanticDefinition(ValueObject):
    """Immutable definition binding linking a moniker to its source location."""

    moniker: SymbolMoniker
    qualified_name: QualifiedName
    path: FilePath
    location: Location


@dataclass(frozen=True, slots=True)
class SemanticReference(ValueObject):
    """Immutable symbol reference linking a usage site to a target moniker."""

    source_moniker: SymbolMoniker
    target_moniker: SymbolMoniker
    path: FilePath
    location: Location


@dataclass(frozen=True, slots=True)
class CallRelation(ValueObject):
    """Immutable function/method invocation relationship."""

    caller_moniker: SymbolMoniker
    callee_moniker: SymbolMoniker
    location: Location


@dataclass(frozen=True, slots=True)
class ImportRelation(ValueObject):
    """Immutable import relationship binding an importing file to an imported symbol."""

    importer_path: FilePath
    imported_symbol_moniker: SymbolMoniker
    alias: Optional[str] = None
    is_relative: bool = False


@dataclass(frozen=True, slots=True)
class InheritanceRelation(ValueObject):
    """Immutable class inheritance or interface implementation relationship."""

    subclass_moniker: SymbolMoniker
    superclass_moniker: SymbolMoniker
    is_interface: bool = False


@dataclass(frozen=True, slots=True)
class SemanticRelation(ValueObject):
    """Generic immutable directional semantic relationship."""

    source: SymbolMoniker
    target: SymbolMoniker
    kind: RelationKind
    location: Location
