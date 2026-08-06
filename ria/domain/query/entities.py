"""Entities and Query Result Containers for C4 Query Engine."""

from dataclasses import dataclass, field
from typing import Optional, Tuple, Union

from ria.domain.common.base import ValueObject
from ria.domain.query.value_objects import QueryCriteria, QueryStatistics, QueryType
from ria.domain.resolution.entities import SemanticSymbol
from ria.domain.resolution.value_objects import (
    CallRelation,
    ImportRelation,
    SemanticDefinition,
    SemanticReference,
    SemanticRelation,
)


@dataclass(frozen=True, slots=True)
class Query(ValueObject):
    """Immutable domain entity representing a requested semantic query."""

    query_id: str
    query_type: QueryType
    criteria: QueryCriteria


@dataclass(frozen=True, slots=True)
class DefinitionResult(ValueObject):
    """Result for GO_TO_DEFINITION query."""

    symbols: Tuple[SemanticSymbol, ...] = field(default_factory=tuple)
    definitions: Tuple[SemanticDefinition, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ReferenceResult(ValueObject):
    """Result for FIND_REFERENCES query."""

    references: Tuple[SemanticReference, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class CallHierarchyResult(ValueObject):
    """Result for FIND_CALLERS and FIND_CALLEES queries."""

    calls: Tuple[CallRelation, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ImportResult(ValueObject):
    """Result for FIND_IMPORTS query."""

    imports: Tuple[ImportRelation, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ExportResult(ValueObject):
    """Result for FIND_EXPORTS query."""

    exports: Tuple[SemanticSymbol, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class DependencyResult(ValueObject):
    """Result for DEPENDENCY_ANALYSIS query."""

    relations: Tuple[SemanticRelation, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class SymbolSearchResult(ValueObject):
    """Result for SYMBOL_SEARCH query."""

    symbols: Tuple[SemanticSymbol, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ModuleSearchResult(ValueObject):
    """Result for MODULE_SEARCH query."""

    modules: Tuple[SemanticSymbol, ...] = field(default_factory=tuple)


QueryResultPayload = Union[
    DefinitionResult,
    ReferenceResult,
    CallHierarchyResult,
    ImportResult,
    ExportResult,
    DependencyResult,
    SymbolSearchResult,
    ModuleSearchResult,
]


@dataclass(frozen=True, slots=True)
class QueryResult(ValueObject):
    """Immutable container holding complete query result payload and performance statistics."""

    query_id: str
    query_type: QueryType
    payload: Optional[QueryResultPayload]
    statistics: QueryStatistics
    is_success: bool = True
    error_message: Optional[str] = None
