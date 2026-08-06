"""Ranking Engine Port Definition."""

from typing import Protocol, Any, List


class RankingEnginePort(Protocol):
    """Port interface for ranking context items."""

    def rank(self, items: List[Any]) -> List[Any]:
        ...
