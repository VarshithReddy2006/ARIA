"""Search Subsystem Package."""

from ria.search.autocomplete import AutocompleteEngine
from ria.search.cache import SearchCache
from ria.search.dto import ExecuteSearchDTO, SearchResponseDTO
from ria.search.engine import SearchEngine
from ria.search.exceptions import (
    SearchExecutionException,
    SearchException,
    SearchIndexException,
)
from ria.search.filters import SearchFilterEngine
from ria.search.highlight import HighlightEngine
from ria.search.index import SearchIndex
from ria.search.planner import SearchPlanner
from ria.search.ranking import RankingEngine

__all__ = [
    "SearchPlanner",
    "SearchIndex",
    "RankingEngine",
    "AutocompleteEngine",
    "SearchFilterEngine",
    "HighlightEngine",
    "SearchCache",
    "SearchEngine",
    "ExecuteSearchDTO",
    "SearchResponseDTO",
    "SearchException",
    "SearchIndexException",
    "SearchExecutionException",
]
