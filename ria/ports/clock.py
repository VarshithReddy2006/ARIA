"""Clock port.

Time is an outbound dependency. Reading the wall clock directly inside a use case
makes the use case non-deterministic and therefore untestable without sleeping,
which contradicts PRD principle P2 ("determinism before probability") and the
testability requirement of the build brief.

Every timestamp recorded by this system is produced through this port, so a test
can assert on exact values and a replay can reproduce them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

__all__ = ["Clock"]


@runtime_checkable
class Clock(Protocol):
    """Source of the current time.

    Implementations must return timezone-aware values in UTC. Naive datetimes are
    forbidden: mixing naive and aware values silently produces wrong durations,
    and duration is what staleness and retention decisions are made from.
    """

    def now(self) -> datetime:
        """Return the current instant as a timezone-aware UTC datetime."""
        ...
