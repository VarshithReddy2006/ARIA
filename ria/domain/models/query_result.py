"""Query result value objects.

Defines QueryMatch, QueryMetadata, QueryStatistics, and QueryResult.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Tuple

__all__ = ["QueryMatch", "QueryMetadata", "QueryStatistics", "QueryResult"]


@dataclass(frozen=True)
class QueryMatch:
    """A single matching result item produced by a query.

    Attributes:
        id: Unique identifier for the matched entity.
        kind: Entity classification kind.
        name: Short name of the matched entity.
        qualified_name: Fully qualified identifier path.
        location_path: File path location.
        score: Relevance or confidence score in [0.0, 1.0].
        properties: Additional metadata dictionary.
    """

    id: str
    kind: str
    name: str
    qualified_name: str
    location_path: Optional[str] = None
    score: float = 1.0
    properties: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"score must be within [0, 1], got {self.score}")


@dataclass(frozen=True)
class QueryMetadata:
    """Metadata accompanying a query execution result.

    Attributes:
        query_id: Identity of the query.
        query_type: Type of query performed.
        created_at_iso: UTC timestamp when the result was generated.
    """

    query_id: str
    query_type: str
    created_at_iso: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class QueryStatistics:
    """Execution statistics for a query request.

    Attributes:
        total_matches: Total matching entities count.
        execution_time_seconds: Execution latency in seconds.
        nodes_traversed: Graph nodes evaluated.
        cache_hit: True if served from query cache.
    """

    total_matches: int = 0
    execution_time_seconds: float = 0.0
    nodes_traversed: int = 0
    cache_hit: bool = False

    def __post_init__(self) -> None:
        if self.total_matches < 0:
            raise ValueError(
                f"total_matches must be non-negative, got {self.total_matches}"
            )
        if self.execution_time_seconds < 0.0:
            raise ValueError(
                f"execution_time_seconds must be non-negative, got {self.execution_time_seconds}"
            )
        if self.nodes_traversed < 0:
            raise ValueError(
                f"nodes_traversed must be non-negative, got {self.nodes_traversed}"
            )


@dataclass(frozen=True)
class QueryResult:
    """Complete result container for a Repository Query.

    Attributes:
        matches: Tuple of QueryMatch entries.
        statistics: Execution statistics.
        metadata: Query metadata.
    """

    matches: Tuple[QueryMatch, ...] = ()
    statistics: QueryStatistics = field(default_factory=QueryStatistics)
    metadata: QueryMetadata = field(
        default_factory=lambda: QueryMetadata(query_id="query", query_type="general")
    )
