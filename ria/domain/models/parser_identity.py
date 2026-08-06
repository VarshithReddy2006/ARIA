"""Parser component versions and the parse cache key.

Implements the cache rule Milestone 3 states verbatim::

    Cache Key = reuse_key + Parser Version + Extractor Version + Language Version
    If any component changes, invalidate cache. Otherwise reuse parse result.

Why four versions and not one
-----------------------------
The three parser components fail independently. A grammar upgrade changes node kinds; an
extractor fix changes which nodes are recognised; a plugin change alters classification.
Collapsing them into one number would work, but it would force every fix to bump a shared
counter, so a Python extractor fix would invalidate every cached Java parse. Keeping them
separate means invalidation is exactly as wide as the change.

This mirrors the versioned cache keys of SDD section 5.5, where "every cache key includes
the producing component's version, so upgrading a component invalidates exactly its own
outputs and nothing else".

Why the key is a value object rather than a formatted string
------------------------------------------------------------
A string key is assembled at each call site, and one site that formats its components in
a different order produces a key that never hits and never errors — a cache that silently
stops working while every test still passes. Constructing the key through one type means
the composition happens once.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Tuple

__all__ = ["ComponentVersion", "ParserFingerprint", "ParseCacheKey"]

#: A component version is a name and a version string. Both are restricted to characters
#: that cannot act as separators in the composed key, so that no version value can forge
#: a boundary and make two distinct fingerprints collide.
_COMPONENT_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")


@dataclass(frozen=True)
class ComponentVersion:
    """The identity and version of one parser component.

    Attributes:
        name: Component identifier, for example ``tree-sitter-python`` or
            ``python-extractor``.
        version: Version string. Compared for equality only, never ordered: cache
            invalidation asks whether the version changed, not whether it increased, and
            a downgrade must invalidate exactly as a upgrade does.
    """

    name: str
    version: str

    def __post_init__(self) -> None:
        for field_name, value in (("name", self.name), ("version", self.version)):
            if not value:
                raise ValueError(f"component {field_name} must be non-empty")
            if not _COMPONENT_TOKEN.match(value):
                raise ValueError(
                    f"component {field_name} may contain only alphanumerics and "
                    f"'.', '_', '+', '-' so it cannot forge a key separator, "
                    f"got {value!r}"
                )

    def __str__(self) -> str:
        return f"{self.name}@{self.version}"


@dataclass(frozen=True)
class ParserFingerprint:
    """The three component versions that together determine a parse result.

    Any change to any of them means a previously cached result may no longer be what
    parsing would now produce, so the result must not be reused.

    Attributes:
        parser: The parsing engine and grammar binding.
        extractor: The extractor set that turned a tree into declarations.
        language: The language plugin declaring the grammar, queries and conventions.
    """

    parser: ComponentVersion
    extractor: ComponentVersion
    language: ComponentVersion

    @property
    def components(self) -> Tuple[ComponentVersion, ComponentVersion, ComponentVersion]:
        """The three components in the fixed order the key composes them."""
        return (self.parser, self.extractor, self.language)

    def token(self) -> str:
        """Canonical string form, used as the version part of a cache key.

        Order is fixed by :attr:`components` rather than by iteration, so the token is
        stable across runs and processes.
        """
        return "|".join(str(component) for component in self.components)

    def digest(self) -> str:
        """Short stable digest of the fingerprint.

        Used where a bounded-length identifier is needed — a filename, a metric label —
        because a full token contains version strings of unbounded length.
        """
        return hashlib.sha256(self.token().encode("utf-8")).hexdigest()[:16]

    def __str__(self) -> str:
        return self.token()


@dataclass(frozen=True)
class ParseCacheKey:
    """Identity of a cached parse result.

    Composed of the file unit's reuse key — content hash plus language, from Twin Spec
    section 6.4 — and the parser fingerprint. Two files with identical content in
    different commits, branches or repositories share a key and are therefore parsed
    once, which is the reuse the content-addressed design exists to enable.

    The key deliberately does not include the file's path, its commit, or its repository.
    Including any of them would make an identical file parsed again in another location a
    cache miss, which would discard the whole benefit.

    Attributes:
        reuse_key: ``content_hash|language`` from
            :attr:`~ria.domain.models.file_unit.FileUnit.reuse_key`.
        fingerprint: The parser component versions.
    """

    reuse_key: str
    fingerprint: ParserFingerprint

    def __post_init__(self) -> None:
        if not self.reuse_key:
            raise ValueError("reuse_key must be non-empty")
        if "\x1e" in self.reuse_key:
            raise ValueError("reuse_key must not contain the key separator")

    def token(self) -> str:
        """Canonical string form of the whole key.

        The record separator between the two halves cannot appear in either, so no
        combination of a reuse key and a fingerprint can produce another key's token.
        """
        return f"{self.reuse_key}\x1e{self.fingerprint.token()}"

    def digest(self) -> str:
        """Fixed-length digest of the key.

        What a storage adapter uses as a primary key: a reuse key contains a content hash
        and a language name, so the composed token has no useful length bound.

        Returns:
            Hexadecimal SHA-256 digest.
        """
        return hashlib.sha256(self.token().encode("utf-8")).hexdigest()

    def with_fingerprint(self, fingerprint: ParserFingerprint) -> "ParseCacheKey":
        """Return the key the same content would have under different component versions.

        Used to check whether a result cached under a previous fingerprint exists, which
        is what makes a version bump observable as a measured invalidation rather than a
        silent drop in hit rate.

        Args:
            fingerprint: Component versions to substitute.
        """
        return ParseCacheKey(reuse_key=self.reuse_key, fingerprint=fingerprint)

    def __str__(self) -> str:
        return f"{self.reuse_key}#{self.fingerprint.digest()}"
