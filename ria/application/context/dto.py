"""Data Transfer Objects for Context Application Layer."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BuildContextCommandDTO:
    """DTO requesting context package assembly."""

    repo_id: str
    question: str
    max_tokens: int = 4000
    format: str = "json"


@dataclass(frozen=True, slots=True)
class ExpandContextCommandDTO:
    """DTO requesting context expansion without serialization."""

    repo_id: str
    symbol_monikers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SerializeContextCommandDTO:
    """DTO requesting serialization of an existing package."""

    package_id: str
    format: str = "markdown"
