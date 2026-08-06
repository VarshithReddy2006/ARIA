"""Progress sink implementations.

Three adapters for :class:`~ria.ports.progress.ProgressSink`, all complete:

:class:`LoggingProgressSink`
    Emits one structured record per event. The default in a deployment.
:class:`InMemoryProgressSink`
    Retains events for inspection. Used by tests and by a synchronous caller that
    wants the trace of a run it just performed.
:class:`CompositeProgressSink`
    Fans out to several sinks, isolating each so one failing sink cannot prevent the
    others from observing.

Every implementation honours the port's contract that a sink must never raise. A
sink that could fail the operation it observes would turn an instrumentation defect
into a failed index build, which is strictly worse than having no instrumentation.
"""

from __future__ import annotations

import logging
import threading
from typing import List, Optional, Sequence, Tuple

from ria.domain.enums import IngestionStage
from ria.domain.models.progress import ProgressEvent
from ria.observability.logging import get_logger
from ria.ports.progress import ProgressSink

__all__ = [
    "LoggingProgressSink",
    "InMemoryProgressSink",
    "CompositeProgressSink",
    "NullProgressSink",
]

_LOGGER = get_logger(__name__)


class LoggingProgressSink:
    """Progress sink writing one structured log record per event.

    Satisfies :class:`~ria.ports.progress.ProgressSink`.

    Args:
        level: Level at which events are emitted. Defaults to ``DEBUG`` because a
            large ingestion produces one event per stage per commit, and emitting
            that at ``INFO`` would drown the records an operator actually reads.
        logger: Logger to write to. Defaults to this module's logger.
    """

    __slots__ = ("_level", "_logger")

    def __init__(
        self, *, level: int = logging.DEBUG, logger: Optional[logging.Logger] = None
    ) -> None:
        self._level = level
        self._logger = logger or _LOGGER

    def emit(self, event: ProgressEvent) -> None:
        """Write one progress record.

        Args:
            event: The observation.
        """
        try:
            self._logger.log(
                self._level,
                "ingestion progress",
                extra={
                    "repository_id": str(event.repository_id),
                    "stage": event.stage.value,
                    "stage_order": event.stage.order,
                    "job_id": event.job_id,
                    "commit": event.commit_sha,
                    "completed": event.completed,
                    "total": event.total,
                    "fraction": event.fraction,
                    "detail": event.message,
                },
            )
        except Exception:  # noqa: BLE001 - a sink must never raise
            # Deliberately swallowed and not re-logged: if logging is the thing
            # that failed, logging the failure would fail too.
            pass


class InMemoryProgressSink:
    """Progress sink retaining events in memory.

    Satisfies :class:`~ria.ports.progress.ProgressSink`. Thread-safe, because the
    worker pool emits from several threads into one sink.

    Args:
        limit: Maximum number of events retained. Once reached, the oldest are
            discarded so a long-running process cannot grow without bound. Counts
            remain exact.
    """

    def __init__(self, *, limit: int = 10_000) -> None:
        if limit < 1:
            raise ValueError("limit must be positive")
        self._limit = limit
        self._lock = threading.Lock()
        self._events: List[ProgressEvent] = []
        self._emitted = 0

    def emit(self, event: ProgressEvent) -> None:
        """Retain one progress observation.

        Args:
            event: The observation.
        """
        with self._lock:
            self._emitted += 1
            self._events.append(event)
            if len(self._events) > self._limit:
                del self._events[0 : len(self._events) - self._limit]

    @property
    def emitted_count(self) -> int:
        """Total events emitted, including any discarded by the retention limit."""
        with self._lock:
            return self._emitted

    def events(self) -> Sequence[ProgressEvent]:
        """Snapshot of the retained events, oldest first."""
        with self._lock:
            return tuple(self._events)

    def events_for_stage(self, stage: IngestionStage) -> Sequence[ProgressEvent]:
        """Retained events for one stage.

        Args:
            stage: Stage to filter by.
        """
        return tuple(event for event in self.events() if event.stage is stage)

    def stages_seen(self) -> Tuple[IngestionStage, ...]:
        """Distinct stages observed, in the order they first appeared.

        Order of first appearance rather than a set, so a test can assert that the
        pipeline ran its stages in the sequence the specification declares.
        """
        seen: List[IngestionStage] = []
        for event in self.events():
            if event.stage not in seen:
                seen.append(event.stage)
        return tuple(seen)

    def last(self) -> Optional[ProgressEvent]:
        """Most recent retained event, or ``None`` if none were emitted."""
        with self._lock:
            return self._events[-1] if self._events else None

    def reset(self) -> None:
        """Discard every retained event and reset the counter."""
        with self._lock:
            self._events.clear()
            self._emitted = 0


class CompositeProgressSink:
    """Progress sink fanning out to several sinks.

    Satisfies :class:`~ria.ports.progress.ProgressSink`. Each delegate is isolated:
    one raising sink does not prevent the others from receiving the event, which is
    the point of composing rather than chaining.

    Args:
        sinks: Delegates to fan out to, in order.
    """

    __slots__ = ("_sinks",)

    def __init__(self, *sinks: ProgressSink) -> None:
        self._sinks: Tuple[ProgressSink, ...] = tuple(sinks)

    def emit(self, event: ProgressEvent) -> None:
        """Forward one observation to every delegate.

        Args:
            event: The observation.
        """
        for sink in self._sinks:
            try:
                sink.emit(event)
            except Exception:  # noqa: BLE001 - a sink must never raise
                _LOGGER.warning(
                    "progress sink raised and was skipped",
                    extra={"sink": type(sink).__name__},
                )


class NullProgressSink:
    """Progress sink that discards every event.

    Satisfies :class:`~ria.ports.progress.ProgressSink`. Selected when progress
    reporting is not wanted, so disabling it removes a sink rather than adding a
    conditional at every emit site.
    """

    __slots__ = ()

    def emit(self, event: ProgressEvent) -> None:
        """Discard one observation.

        Args:
            event: Ignored.
        """
        return None
