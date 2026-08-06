"""Context Management Component.

Provides contextvars and helper context managers for tracking request IDs,
build IDs, repository names, and analysis phases across async/sync tasks.
"""

from __future__ import annotations

import contextvars
import uuid
from typing import Optional

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default=""
)
build_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "build_id", default=""
)
repository_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "repository", default=""
)
analysis_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "analysis", default=""
)


def get_current_request_id() -> str:
    """Return the active request ID or empty string if not bound."""
    return request_id_var.get()


class RequestContext:
    """Context manager for binding request/trace context to the active execution thread/async task."""

    def __init__(
        self,
        request_id: Optional[str] = None,
        build_id: Optional[str] = None,
        repository: Optional[str] = None,
        analysis: Optional[str] = None,
    ) -> None:
        self.request_id = request_id or str(uuid.uuid4())
        self.build_id = build_id
        self.repository = repository
        self.analysis = analysis
        self._tokens = []

    def __enter__(self) -> "RequestContext":
        self._tokens.append(request_id_var.set(self.request_id))
        if self.build_id:
            self._tokens.append(build_id_var.set(self.build_id))
        if self.repository:
            self._tokens.append(repository_var.set(self.repository))
        if self.analysis:
            self._tokens.append(analysis_var.set(self.analysis))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if request_id_var.get() == self.request_id:
            request_id_var.set("")
        if self.build_id and build_id_var.get() == self.build_id:
            build_id_var.set("")
        if self.repository and repository_var.get() == self.repository:
            repository_var.set("")
        if self.analysis and analysis_var.get() == self.analysis:
            analysis_var.set("")
