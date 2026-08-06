"""Execution result and metadata value objects.

Defines ExecutionMetadata, ExecutionFingerprint, and ExecutionCacheKey.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib

__all__ = [
    "ExecutionMetadata",
    "ExecutionFingerprint",
    "ExecutionCacheKey",
]


@dataclass(frozen=True)
class ExecutionMetadata:
    """Provenance metadata for repository execution.

    Attributes:
        execution_id_str: ExecutionId value string.
        created_at_iso: UTC creation timestamp.
    """

    execution_id_str: str
    created_at_iso: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class ExecutionFingerprint:
    """Fingerprint representing repository execution specification and target.

    Attributes:
        workflow_id_str: Parent workflow ID string.
        commit_sha_str: Target commit SHA string.
    """

    workflow_id_str: str
    commit_sha_str: str

    def token(self) -> str:
        """Return canonical token string."""
        return f"{self.workflow_id_str}:{self.commit_sha_str}"

    def digest(self) -> str:
        """Compute SHA-256 hex digest of fingerprint token."""
        return hashlib.sha256(self.token().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ExecutionCacheKey:
    """Content-addressed lookup key for repository execution cache.

    Attributes:
        fingerprint: ExecutionFingerprint.
    """

    fingerprint: ExecutionFingerprint

    def digest(self) -> str:
        """Compute SHA-256 hex digest of cache key."""
        raw = f"exc_cache:{self.fingerprint.digest()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
