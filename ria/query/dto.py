"""Data Transfer Objects for Query Engine Subsystem."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class ExecuteQueryDTO:
    """DTO requesting query execution."""

    query_id: str
    query_type: str
    symbol_moniker: Optional[str] = None
    symbol_name: Optional[str] = None
    file_path: Optional[str] = None
    max_results: int = 100


@dataclass(frozen=True, slots=True)
class QueryResponseDTO:
    """DTO summarizing query response to caller."""

    query_id: str
    query_type: str
    total_results: int
    elapsed_ms: float
    cache_hit: bool
    is_success: bool
    error_message: Optional[str] = None
