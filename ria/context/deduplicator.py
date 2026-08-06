"""Deduplicator for Context Snippets."""

from collections.abc import Sequence

from ria.domain.context.entities import ContextSnippet


class Deduplicator:
    """Engine removing duplicate context snippets while preserving stable rank ordering."""

    def deduplicate(
        self,
        snippets: Sequence[ContextSnippet],
    ) -> Sequence[ContextSnippet]:
        unique_snippets: list[ContextSnippet] = []
        seen_keys: set[tuple[str, str]] = set()

        for snip in snippets:
            key = (snip.citation.symbol_moniker.value, snip.content)
            if key not in seen_keys:
                seen_keys.add(key)
                unique_snippets.append(snip)

        return tuple(unique_snippets)
