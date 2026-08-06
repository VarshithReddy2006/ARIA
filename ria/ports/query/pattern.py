"""Pattern Matching Port Definition."""

from typing import Protocol, Any


class PatternMatchingPort(Protocol):
    """Port interface for pattern matching."""

    def match_patterns(self, target: Any) -> Any: ...
