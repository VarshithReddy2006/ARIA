"""Value Objects for C6 Search Engine."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple

from ria.domain.common.base import ValueObject
from ria.domain.index.value_objects import FilePath, Language
from ria.domain.resolution.entities import SemanticSymbol
from ria.domain.resolution.value_objects import SymbolKind, Visibility
from ria.domain.search.exceptions import InvalidSearchQueryError


class SearchQueryType(Enum):
    """Supported search match strategies."""

    EXACT = "EXACT"
    QUALIFIED_NAME = "QUALIFIED_NAME"
    PREFIX = "PREFIX"
    CAMEL_CASE = "CAMEL_CASE"
    FUZZY = "FUZZY"
    MODULE = "MODULE"
    PACKAGE = "PACKAGE"
    FILE = "FILE"
    PATH = "PATH"
    AUTOCOMPLETE = "AUTOCOMPLETE"


@dataclass(frozen=True, slots=True)
class SearchFilter(ValueObject):
    """Immutable search filters."""

    language: Optional[Language] = None
    symbol_kind: Optional[SymbolKind] = None
    visibility: Optional[Visibility] = None
    file_extension: Optional[str] = None


@dataclass(frozen=True, slots=True)
class SearchScope(ValueObject):
    """Immutable search evaluation scope."""

    file_paths: Tuple[FilePath, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class SearchOptions(ValueObject):
    """Immutable options parameterizing search execution."""

    filters: SearchFilter = field(default_factory=SearchFilter)
    scope: SearchScope = field(default_factory=SearchScope)
    max_results: int = 50

    def _validate_invariants(self) -> None:
        if self.max_results <= 0:
            raise InvalidSearchQueryError("max_results must be greater than zero.")


@dataclass(frozen=True, slots=True)
class SearchQuery(ValueObject):
    """Immutable domain representation of a search request."""

    query_text: str
    query_type: SearchQueryType
    options: SearchOptions = field(default_factory=SearchOptions)

    def _validate_invariants(self) -> None:
        if not self.query_text and self.query_type != SearchQueryType.AUTOCOMPLETE:
            raise InvalidSearchQueryError("query_text cannot be empty.")


@dataclass(frozen=True, slots=True)
class SearchStatistics(ValueObject):
    """Immutable search performance and execution statistics."""

    planning_ms: float
    matching_ms: float
    ranking_ms: float
    total_candidates: int
    cache_hit: bool = False


@dataclass(frozen=True, slots=True)
class SearchScore(ValueObject):
    """Immutable deterministic relevance score for a search result."""

    score_value: float
    match_kind: str


@dataclass(frozen=True, slots=True)
class SearchIndexEntry(ValueObject):
    """Immutable entry inside in-memory SearchIndex."""

    symbol: SemanticSymbol
    tokens: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class AutocompleteSuggestion(ValueObject):
    """Immutable suggestion returned by AutocompleteEngine."""

    text: str
    category: str
    score: float
