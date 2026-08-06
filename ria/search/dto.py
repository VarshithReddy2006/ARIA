"""Data Transfer Objects for Search Subsystem."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class ExecuteSearchDTO:
    """DTO requesting search query execution."""

    repo_id: str
    query_text: str
    query_type: str = "EXACT"
    max_results: int = 50


@dataclass(frozen=True, slots=True)
class SearchResponseDTO:
    """DTO summarizing search response."""

    query_id: str
    total_matches: int
    elapsed_ms: float
    cache_hit: bool
    is_success: bool
    error_message: Optional[str] = None
