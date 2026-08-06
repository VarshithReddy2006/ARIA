"""Query identity value objects.

Defines QueryFingerprint and QueryCacheKey for content-addressed query result caching.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

from ria.domain.identity import CommitSha, RepositoryId

__all__ = ["QueryFingerprint", "QueryCacheKey"]


@dataclass(frozen=True)
class QueryFingerprint:
    """Fingerprint representing a query's structure, type, target, and filter options.

    Attributes:
        query_type: Type/kind of query.
        target_name: Target query argument string.
        filter_token: Serialized string token of filter options.
    """

    query_type: str
    target_name: str = ""
    filter_token: str = ""

    def token(self) -> str:
        """Return canonical token string."""
        return f"{self.query_type}:{self.target_name}:{self.filter_token}"

    def digest(self) -> str:
        """Compute SHA-256 hex digest of the query fingerprint token."""
        return hashlib.sha256(self.token().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class QueryCacheKey:
    """Content-addressed lookup key for query result caching.

    Attributes:
        repository_id: Repository identity.
        commit_sha: Commit SHA.
        fingerprint: QueryFingerprint.
    """

    repository_id: RepositoryId
    commit_sha: CommitSha
    fingerprint: QueryFingerprint

    def digest(self) -> str:
        """Compute SHA-256 hex digest of the cache key."""
        raw = f"query_cache:{self.repository_id.value}:{self.commit_sha.value}:{self.fingerprint.digest()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
