"""C6 Search Domain Package."""

from ria.domain.search.entities import (
    AutocompleteResult,
    FileResult,
    ModuleResult,
    PackageResult,
    SearchResponse,
    SearchResult,
    SearchResultPayload,
    SymbolResult,
)
from ria.domain.search.exceptions import (
    InvalidSearchQueryError,
    SearchDomainException,
    SearchPlanningError,
)
from ria.domain.search.value_objects import (
    AutocompleteSuggestion,
    SearchFilter,
    SearchIndexEntry,
    SearchOptions,
    SearchQuery,
    SearchQueryType,
    SearchScope,
    SearchScore,
    SearchStatistics,
)

__all__ = [
    "SearchQueryType",
    "SearchFilter",
    "SearchScope",
    "SearchOptions",
    "SearchQuery",
    "SearchStatistics",
    "SearchScore",
    "SearchIndexEntry",
    "AutocompleteSuggestion",
    "SymbolResult",
    "FileResult",
    "ModuleResult",
    "PackageResult",
    "AutocompleteResult",
    "SearchResultPayload",
    "SearchResult",
    "SearchResponse",
    "SearchDomainException",
    "InvalidSearchQueryError",
    "SearchPlanningError",
]
