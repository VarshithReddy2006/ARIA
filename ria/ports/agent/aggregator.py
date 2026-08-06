"""Result Aggregator Port Definition."""

from typing import Protocol, Any


class ResultAggregatorPort(Protocol):
    """Port interface for result aggregation."""

    def aggregate(self, results: Any) -> Any:
        ...
