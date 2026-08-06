"""Clock Port abstraction for system time."""

from typing import Protocol, runtime_checkable

from ria.domain.common.value_objects import Timestamp


@runtime_checkable
class ClockPort(Protocol):
    """Protocol for abstracting current system time and monotonic time measurements.

    Preconditions: System clock must be synchronized to UTC.
    Postconditions: Returns UTC timestamps and high-resolution monotonic float values.
    """

    def now_utc(self) -> Timestamp:
        """Return current wall-clock time as a domain Timestamp object."""
        ...

    def monotonic_seconds(self) -> float:
        """Return high-resolution monotonic timer reading in fractional seconds."""
        ...
