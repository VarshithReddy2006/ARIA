"""Context Cache Store Port Definition."""

from typing import Protocol, Any, Optional


class ContextCacheStore(Protocol):
    """Port interface for caching context."""

    def get(self, key: str) -> Optional[Any]: ...

    def put(self, key: str, value: Any) -> None: ...
