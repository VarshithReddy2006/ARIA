"""Intent Classifier Port Definition."""

from typing import Protocol, Any


class IntentClassifierPort(Protocol):
    """Port interface for intent classification."""

    def classify(self, query: str) -> Any:
        ...
