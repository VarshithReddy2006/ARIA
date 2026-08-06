"""Entities and Result Containers for C6 Search Engine."""

from dataclasses import dataclass, field
from typing import Optional, Tuple, Union

from ria.domain.common.base import ValueObject
from ria.domain.index.value_objects import FilePath
from ria.domain.resolution.entities import SemanticSymbol
from ria.domain.search.value_objects import (
    AutocompleteSuggestion,
    SearchQuery,
    SearchScore,
    SearchStatistics,
)


@dataclass(frozen=True, slots=True)
class SymbolResult(ValueObject):
    """Result for symbol search."""

    symbol: SemanticSymbol
    score: SearchScore
    highlighted_name: str


@dataclass(frozen=True, slots=True)
class FileResult(ValueObject):
    """Result for file search."""

    path: FilePath
    score: SearchScore
    highlighted_path: str


@dataclass(frozen=True, slots=True)
class ModuleResult(ValueObject):
    """Result for module search."""

    symbol: SemanticSymbol
    score: SearchScore
    highlighted_name: str


@dataclass(frozen=True, slots=True)
class PackageResult(ValueObject):
    """Result for package search."""

    package_name: str
    score: SearchScore


@dataclass(frozen=True, slots=True)
class AutocompleteResult(ValueObject):
    """Result for autocomplete query."""

    suggestions: Tuple[AutocompleteSuggestion, ...] = field(default_factory=tuple)


SearchResultPayload = Union[
    Tuple[SymbolResult, ...],
    Tuple[FileResult, ...],
    Tuple[ModuleResult, ...],
    Tuple[PackageResult, ...],
    AutocompleteResult,
]


@dataclass(frozen=True, slots=True)
class SearchResult(ValueObject):
    """Container holding typed search result payload."""

    payload: SearchResultPayload


@dataclass(frozen=True, slots=True)
class SearchResponse(ValueObject):
    """Immutable response entity returned by SearchEngine."""

    query_id: str
    query: SearchQuery
    results: SearchResult
    statistics: SearchStatistics
    is_success: bool = True
    error_message: Optional[str] = None
