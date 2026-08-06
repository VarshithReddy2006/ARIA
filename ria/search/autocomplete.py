"""Autocomplete Engine implementing AutocompletePort."""

from collections.abc import Sequence

from ria.domain.search.value_objects import AutocompleteSuggestion, SearchIndexEntry
from ria.ports.search.autocomplete import AutocompletePort


class AutocompleteEngine(AutocompletePort):
    """Engine providing top-ranked suggestions for prefix and camelcase inputs."""

    def suggest(
        self,
        prefix: str,
        candidates: Sequence[SearchIndexEntry],
        max_suggestions: int = 10,
    ) -> Sequence[AutocompleteSuggestion]:
        p_lower = prefix.lower()
        suggestions: list[AutocompleteSuggestion] = []

        seen: set[str] = set()

        for entry in candidates:
            name = entry.symbol.name
            if name in seen:
                continue
            n_lower = name.lower()

            if n_lower.startswith(p_lower):
                suggestions.append(AutocompleteSuggestion(text=name, category="prefix", score=0.9))
                seen.add(name)
            elif p_lower in n_lower:
                suggestions.append(AutocompleteSuggestion(text=name, category="substring", score=0.6))
                seen.add(name)

            if len(suggestions) >= max_suggestions:
                break

        suggestions.sort(key=lambda s: s.score, reverse=True)
        return tuple(suggestions)
