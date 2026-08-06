"""System Clock Adapter implementing ClockPort."""

import time
from datetime import datetime, timezone

from ria.domain.common.value_objects import Timestamp
from ria.ports.common.clock import ClockPort


class SystemClockAdapter(ClockPort):
    """Real system clock implementation using Python standard library time and datetime."""

    def now_utc(self) -> Timestamp:
        """Return current wall-clock time in UTC as a domain Timestamp value object."""
        return Timestamp(iso_format=datetime.now(timezone.utc).isoformat())

    def monotonic_seconds(self) -> float:
        """Return high-resolution monotonic clock seconds."""
        return time.monotonic()
