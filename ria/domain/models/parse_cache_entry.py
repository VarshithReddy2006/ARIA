"""Domain representation of a cached parse result entry.

Wraps a :class:`~ria.domain.models.parse_result.ParseResult` along with its authoritative
:class:`~ria.domain.models.parser_identity.ParseCacheKey` and caching metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ria.domain.models.parse_result import ParseResult
from ria.domain.models.parser_identity import ParseCacheKey, ParserFingerprint

__all__ = ["ParseCacheEntry"]


@dataclass(frozen=True)
class ParseCacheEntry:
    """A parse result as stored in or retrieved from the parse cache.

    Attributes:
        key: Authoritative cache key composed of unit reuse_key + parser fingerprint.
        result: The stored parse result.
        cached_at: Time when the result was placed into the cache (UTC).
    """

    key: ParseCacheKey
    result: ParseResult
    cached_at: datetime

    def __post_init__(self) -> None:
        if self.key.reuse_key != self.result.reuse_key:
            raise ValueError(
                f"cache key reuse_key ({self.key.reuse_key!r}) disagrees with parse result "
                f"reuse_key ({self.result.reuse_key!r})"
            )
        if self.key.fingerprint != self.result.fingerprint:
            raise ValueError(
                f"cache key fingerprint ({self.key.fingerprint!r}) disagrees with parse result "
                f"fingerprint ({self.result.fingerprint!r})"
            )
        if self.cached_at.tzinfo is None:
            raise ValueError("cached_at datetime must be timezone-aware (UTC)")

    def matches_fingerprint(self, fingerprint: ParserFingerprint) -> bool:
        """Check if this cached entry was produced under the given component fingerprint.

        Args:
            fingerprint: Target fingerprint to compare against.

        Returns:
            ``True`` if fingerprints match exactly.
        """
        return self.key.fingerprint == fingerprint

    def as_result(self) -> ParseResult:
        """Return the parse result marked as retrieved from cache.

        Returns:
            A copy of the parse result with ``from_cache=True``.
        """
        return self.result.as_cached()

    def __str__(self) -> str:
        return f"ParseCacheEntry({self.key}, cached_at={self.cached_at.isoformat()})"
