"""Digital Twin Identity domain value objects.

Defines TwinVersion, TwinFingerprint, and TwinCacheKey for content-addressed identity.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

from ria.domain.identity import CommitSha, RepositoryId

__all__ = ["TwinVersion", "TwinFingerprint", "TwinCacheKey"]


@dataclass(frozen=True)
class TwinVersion:
    """Version metadata for a Digital Twin schema and builder.

    Attributes:
        twin_version: Version of the twin specification.
        schema_version: Version of the twin persistence schema.
        builder_version: Version of the twin builder implementation.
    """

    twin_version: str = "1.0.0"
    schema_version: str = "1.0.0"
    builder_version: str = "1.0.0"

    def token(self) -> str:
        """Return canonical version token string."""
        return f"{self.twin_version}:{self.schema_version}:{self.builder_version}"


@dataclass(frozen=True)
class TwinFingerprint:
    """Identity of the builder component, schema, and version producing a twin.

    Attributes:
        builder_name: Name of the twin builder service.
        version: TwinVersion configuration.
    """

    builder_name: str
    version: TwinVersion = TwinVersion()

    def token(self) -> str:
        """Return canonical token string."""
        return f"{self.builder_name}:{self.version.token()}"

    def digest(self) -> str:
        """Compute SHA-256 hex digest of the fingerprint token."""
        return hashlib.sha256(self.token().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TwinCacheKey:
    """Content-addressed lookup key for digital twin caching.

    Attributes:
        repository_id: RepositoryId identity.
        commit_sha: CommitSha identifying snapshot state.
        fingerprint: TwinFingerprint.
    """

    repository_id: RepositoryId
    commit_sha: CommitSha
    fingerprint: TwinFingerprint

    @property
    def reuse_key(self) -> str:
        """Return the commit sha as string reuse key."""
        return self.commit_sha.value

    def digest(self) -> str:
        """Compute SHA-256 hex digest of the cache key."""
        raw = f"twin_cache:{self.repository_id.value}:{self.commit_sha.value}:{self.fingerprint.digest()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
