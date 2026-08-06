"""Compression Engine Port Definition."""

from typing import Protocol, Any


class CompressionEnginePort(Protocol):
    """Port interface for context compression."""

    def compress(self, context: Any) -> Any: ...
