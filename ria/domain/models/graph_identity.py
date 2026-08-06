"""Graph Identity domain value objects.

Defines GraphFingerprint and GraphCacheKey for content-addressed cache identity.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

from ria.domain.identity import CommitSha

__all__ = ["GraphFingerprint", "GraphCacheKey"]


@dataclass(frozen=True)
class GraphFingerprint:
    """Identity of the builder component and schema producing a graph.

    Attributes:
        builder_name: Name of the graph builder service.
        builder_version: Version of the graph builder service.
        schema_version: Version of the graph schema.
    """

    builder_name: str
    builder_version: str
    schema_version: str = "1.0.0"

    def token(self) -> str:
        """Return canonical token string."""
        return f"{self.builder_name}:{self.builder_version}:{self.schema_version}"

    def digest(self) -> str:
        """Compute SHA-256 hex digest of the fingerprint token."""
        return hashlib.sha256(self.token().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class GraphCacheKey:
    """Content-addressed lookup key for graph caching.

    Attributes:
        commit_sha: Commit SHA identifying repository snapshot state.
        fingerprint: GraphFingerprint.
    """

    commit_sha: CommitSha
    fingerprint: GraphFingerprint

    @property
    def reuse_key(self) -> str:
        """Return the commit sha as string reuse key."""
        return self.commit_sha.value

    def digest(self) -> str:
        """Compute SHA-256 hex digest of the cache key."""
        raw = f"graph_cache:{self.commit_sha.value}:{self.fingerprint.digest()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
