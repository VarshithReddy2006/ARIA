"""Data Transfer Objects for Search Application Layer."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SearchSymbolDTO:
    """DTO requesting symbol search."""

    repo_id: str
    query_text: str
    query_type: str = "EXACT"
    max_results: int = 50


@dataclass(frozen=True, slots=True)
class SearchFileDTO:
    """DTO requesting file or path search."""

    repo_id: str
    query_text: str
    max_results: int = 50


@dataclass(frozen=True, slots=True)
class SearchModuleDTO:
    """DTO requesting module or package search."""

    repo_id: str
    query_text: str
    max_results: int = 50


@dataclass(frozen=True, slots=True)
class AutocompleteDTO:
    """DTO requesting autocomplete suggestions."""

    repo_id: str
    prefix: str
    max_suggestions: int = 10
