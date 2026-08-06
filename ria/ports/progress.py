"""Progress reporting port.

The pipeline emits :class:`~ria.domain.models.progress.ProgressEvent` values through
this port so that ingestion is observable without the application layer knowing
whether the destination is a log, a metrics sink, an HTTP stream or a test's list.

Contract
--------
Implementations must never raise and never block. A progress sink is an observer, and
an observer that can fail the operation it observes is worse than no observer at all —
it converts an instrumentation defect into a failed index build. Implementations that
perform I/O must swallow and log their own failures.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ria.domain.models.progress import ProgressEvent

__all__ = ["ProgressSink"]


@runtime_checkable
class ProgressSink(Protocol):
    """Destination for pipeline progress events."""

    def emit(self, event: ProgressEvent) -> None:
        """Record one progress observation.

        Must not raise and must not block.

        Args:
            event: The observation.
        """
        ...
