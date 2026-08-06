"""Query request value objects.

Defines QueryContext, QueryFilter, QueryProjection, and QueryRequest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.query_id import QueryId

__all__ = ["QueryContext", "QueryFilter", "QueryProjection", "QueryRequest"]


@dataclass(frozen=True)
class QueryContext:
    """Execution context for a repository query.

    Attributes:
        repository_id: Identity of the target repository.
        commit_sha: Bound commit SHA.
        max_results: Upper bound on returned matches.
        timeout_seconds: Maximum allowed query execution time.
    """

    repository_id: RepositoryId
    commit_sha: CommitSha
    max_results: int = 1000
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.max_results <= 0:
            raise ValueError(f"max_results must be positive, got {self.max_results}")
        if self.timeout_seconds <= 0.0:
            raise ValueError(
                f"timeout_seconds must be positive, got {self.timeout_seconds}"
            )


@dataclass(frozen=True)
class QueryFilter:
    """Filtering criteria applied to query execution.

    Attributes:
        kinds: Target entity or node kinds to match.
        file_paths: Restrict search to specific file paths.
        languages: Restrict search to specific languages.
        name_pattern: Optional glob or regex substring pattern.
    """

    kinds: Tuple[str, ...] = ()
    file_paths: Tuple[str, ...] = ()
    languages: Tuple[str, ...] = ()
    name_pattern: Optional[str] = None


@dataclass(frozen=True)
class QueryProjection:
    """Fields to project into matching query results.

    Attributes:
        include_locations: Whether to populate location paths and spans.
        include_signatures: Whether to include type/callable signatures.
        include_metrics: Whether to attach node/symbol metrics.
    """

    include_locations: bool = True
    include_signatures: bool = True
    include_metrics: bool = False


@dataclass(frozen=True)
class QueryRequest:
    """Complete Repository Query request.

    Attributes:
        query_id: Unique QueryId.
        context: Bound QueryContext.
        query_type: Kind of query (e.g. 'find_symbol', 'find_references', 'calls').
        target_name: Target symbol, file, or node identifier.
        filter: Active QueryFilter options.
        projection: Active QueryProjection options.
    """

    query_id: QueryId
    context: QueryContext
    query_type: str
    target_name: Optional[str] = None
    filter: QueryFilter = field(default_factory=QueryFilter)
    projection: QueryProjection = field(default_factory=QueryProjection)
