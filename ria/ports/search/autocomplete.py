"""Autocomplete Port Protocol."""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ria.domain.search.value_objects import AutocompleteSuggestion, SearchIndexEntry


@runtime_checkable
class AutocompletePort(Protocol):
    """Protocol generating autocomplete suggestions for user search inputs."""

    def suggest(
        self,
        prefix: str,
        candidates: Sequence[SearchIndexEntry],
        max_suggestions: int = 10,
    ) -> Sequence[AutocompleteSuggestion]:
        """Generate top-ranked suggestions for prefix."""
        ...
