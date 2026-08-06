"""Data Transfer Objects for Query Application Layer."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class SearchSymbolQueryDTO:
    """DTO requesting symbol or module search."""

    repo_id: str
    symbol_name: str
    max_results: int = 50


@dataclass(frozen=True, slots=True)
class FindDefinitionQueryDTO:
    """DTO requesting definition lookup."""

    repo_id: str
    symbol_moniker: Optional[str] = None
    symbol_name: Optional[str] = None


@dataclass(frozen=True, slots=True)
class FindReferencesQueryDTO:
    """DTO requesting symbol references lookup."""

    repo_id: str
    symbol_moniker: str


@dataclass(frozen=True, slots=True)
class CallHierarchyQueryDTO:
    """DTO requesting caller or callee hierarchy lookup."""

    repo_id: str
    symbol_moniker: str
    is_callers: bool = True


@dataclass(frozen=True, slots=True)
class DependencyQueryDTO:
    """DTO requesting dependency analysis."""

    repo_id: str
    symbol_moniker: Optional[str] = None
    file_path: Optional[str] = None
