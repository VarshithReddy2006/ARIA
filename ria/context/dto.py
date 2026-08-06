"""Data Transfer Objects for Context Subsystem."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class BuildContextDTO:
    """DTO requesting context package assembly."""

    repo_id: str
    question: str
    max_tokens: int = 4000
    format: str = "json"


@dataclass(frozen=True, slots=True)
class ContextResponseDTO:
    """DTO summarizing context build response."""

    package_id: str
    total_sections: int
    total_snippets: int
    total_tokens: int
    content: str
    elapsed_ms: float
    is_success: bool
    error_message: Optional[str] = None
