"""System clock adapter."""

from __future__ import annotations

from datetime import datetime, timezone

__all__ = ["SystemClock"]


class SystemClock:
    """Clock backed by the host's wall clock.

    Always returns timezone-aware UTC values, as the
    :class:`~ria.ports.clock.Clock` contract requires. Naive datetimes are never
    produced, because mixing naive and aware values silently corrupts every
    duration computed from them, and durations drive staleness and retention.

    Satisfies :class:`~ria.ports.clock.Clock`.
    """

    __slots__ = ()

    def now(self) -> datetime:
        """Return the current instant as a timezone-aware UTC datetime."""
        return datetime.now(timezone.utc)
