"""Application Exceptions for Context Builder Subsystem."""


class ContextException(Exception):
    """Base exception for Context Builder failures."""

    pass


class ContextExpansionException(ContextException):
    """Raised when context expansion fails."""

    pass


class ContextOptimizationException(ContextException):
    """Raised when budget optimization fails."""

    pass
