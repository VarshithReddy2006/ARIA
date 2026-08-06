"""Ranking Engine implementing RankingEnginePort."""

import re
from collections.abc import Sequence

from ria.domain.search.value_objects import SearchIndexEntry, SearchQuery, SearchScore
from ria.ports.search.ranking import RankingEnginePort


class RankingEngine(RankingEnginePort):
    """Deterministic RankingEngine scoring candidates based on strict match priority."""

    def _is_camel_case_match(self, text: str, query: str) -> bool:
        uppercase = "".join(c for c in text if c.isupper())
        return query.upper() in uppercase

    def _score_entry(self, entry: SearchIndexEntry, query_text: str) -> SearchScore:
        sym_name = entry.symbol.name
        q_lower = query_text.lower()
        name_lower = sym_name.lower()

        # 1. Exact match
        if sym_name == query_text or name_lower == q_lower:
            return SearchScore(score_value=1.0, match_kind="EXACT")

        # 2. Qualified name match
        if entry.symbol.qualified_name.dotted_path.lower() == q_lower:
            return SearchScore(score_value=0.9, match_kind="QUALIFIED_NAME")

        # 3. Prefix match
        if name_lower.startswith(q_lower):
            return SearchScore(score_value=0.8, match_kind="PREFIX")

        # 4. CamelCase match
        if self._is_camel_case_match(sym_name, query_text):
            return SearchScore(score_value=0.7, match_kind="CAMEL_CASE")

        # 5. Substring match
        if q_lower in name_lower:
            return SearchScore(score_value=0.6, match_kind="SUBSTRING")

        # 6. Fuzzy match
        if all(char in name_lower for char in q_lower):
            return SearchScore(score_value=0.5, match_kind="FUZZY")

        # 7. File path match
        if q_lower in entry.symbol.path.relative_path.lower():
            return SearchScore(score_value=0.4, match_kind="FILE_PATH")

        return SearchScore(score_value=0.0, match_kind="NONE")

    def rank_candidates(
        self,
        query: SearchQuery,
        candidates: Sequence[SearchIndexEntry],
    ) -> Sequence[tuple[SearchIndexEntry, SearchScore]]:
        scored: list[tuple[SearchIndexEntry, SearchScore]] = []
        for entry in candidates:
            score = self._score_entry(entry, query.query_text)
            if score.score_value > 0.0:
                scored.append((entry, score))

        scored.sort(key=lambda item: item[1].score_value, reverse=True)
        return tuple(scored[: query.options.max_results])
