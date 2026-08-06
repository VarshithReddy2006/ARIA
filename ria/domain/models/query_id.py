"""QueryId value object.

Identifies a single Repository Query execution request or cached query result.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

__all__ = ["QueryId"]


@dataclass(frozen=True)
class QueryId:
    """Opaque, immutable identifier for a query request.

    Attributes:
        value: Non-empty string key.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("QueryId value must be a non-empty string")

    @classmethod
    def for_query(cls, query_type: str, target: str) -> QueryId:
        """Construct a deterministic QueryId for a query type and target string.

        Args:
            query_type: Type/kind of query.
            target: Query target name or expression.

        Returns:
            Deterministic QueryId.
        """
        raw_key = f"query:{query_type}:{target}"
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]
        return cls(f"qry_{query_type[:4]}_{digest}")

    def __str__(self) -> str:
        return self.value
