"""Value Objects for C4 Query Engine."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ria.domain.common.base import ValueObject
from ria.domain.index.value_objects import FilePath
from ria.domain.query.exceptions import InvalidQueryCriteriaError
from ria.domain.resolution.value_objects import SymbolMoniker


class QueryType(Enum):
    """Supported semantic repository query types."""

    GO_TO_DEFINITION = "GO_TO_DEFINITION"
    FIND_REFERENCES = "FIND_REFERENCES"
    FIND_CALLERS = "FIND_CALLERS"
    FIND_CALLEES = "FIND_CALLEES"
    FIND_IMPORTS = "FIND_IMPORTS"
    FIND_EXPORTS = "FIND_EXPORTS"
    DEPENDENCY_ANALYSIS = "DEPENDENCY_ANALYSIS"
    SYMBOL_SEARCH = "SYMBOL_SEARCH"
    MODULE_SEARCH = "MODULE_SEARCH"


@dataclass(frozen=True, slots=True)
class QueryCriteria(ValueObject):
    """Immutable criteria filtering query evaluation."""

    symbol_moniker: Optional[SymbolMoniker] = None
    symbol_name: Optional[str] = None
    file_path: Optional[FilePath] = None
    max_results: int = 100

    def _validate_invariants(self) -> None:
        if self.max_results <= 0:
            raise InvalidQueryCriteriaError("max_results must be greater than zero.")


@dataclass(frozen=True, slots=True)
class QueryStatistics(ValueObject):
    """Immutable performance and execution statistics for a query."""

    planning_duration_ms: float
    execution_duration_ms: float
    total_records_scanned: int
    cache_hit: bool = False


@dataclass(frozen=True, slots=True)
class QueryPlan(ValueObject):
    """Immutable logical execution plan for a semantic query."""

    query_id: str
    query_type: QueryType
    criteria: QueryCriteria
