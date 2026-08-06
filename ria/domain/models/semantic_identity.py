"""Semantic identity and cache key domain models.

Implements component fingerprinting and content-addressed cache keys for semantic artifacts.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ria.domain.identity import ContentHash
from ria.domain.models.parser_identity import ComponentVersion, ParserFingerprint

__all__ = ["SemanticFingerprint", "SemanticCacheKey"]


@dataclass(frozen=True)
class SemanticFingerprint:
    """Immutable identity of the semantic resolver components.

    Attributes:
        resolver_name: Name of the semantic resolver.
        resolver_version: Version of the semantic resolver.
        parser_fingerprint: Fingerprint of the parser layer components.
        language: Canonical language name.
    """

    resolver_name: str
    resolver_version: str
    parser_fingerprint: ParserFingerprint
    language: str

    def __post_init__(self) -> None:
        if not self.resolver_name or not self.resolver_name.strip():
            raise ValueError("resolver_name must be non-empty")
        if not self.resolver_version or not self.resolver_version.strip():
            raise ValueError("resolver_version must be non-empty")
        if not self.language or not self.language.strip():
            raise ValueError("language must be non-empty")

    @property
    def resolver_version_obj(self) -> ComponentVersion:
        """Return ComponentVersion for this resolver."""
        return ComponentVersion(name=self.resolver_name, version=self.resolver_version)

    def digest(self) -> str:
        """Calculate SHA-256 digest over component versions."""
        raw = f"{self.resolver_name}:{self.resolver_version}:{self.parser_fingerprint.digest()}:{self.language}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def token(self) -> str:
        """Human-readable component string."""
        return f"sem:{self.language}:{self.resolver_name}@{self.resolver_version}+{self.parser_fingerprint.token()}"


@dataclass(frozen=True)
class SemanticCacheKey:
    """Immutable content-addressed cache key for semantic resolution results.

    Attributes:
        content_hash: Physical identity of source bytes.
        language: Canonical language name.
        fingerprint: SemanticFingerprint of parser + resolver components.
    """

    content_hash: ContentHash
    language: str
    fingerprint: SemanticFingerprint

    def __post_init__(self) -> None:
        if not self.language or not self.language.strip():
            raise ValueError("language must be non-empty")

    @property
    def reuse_key(self) -> str:
        """Cache reuse key across commits."""
        return f"{self.content_hash.value}|{self.language}"

    def digest(self) -> str:
        """Calculate SHA-256 cache key digest."""
        raw = f"{self.reuse_key}|{self.fingerprint.digest()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
