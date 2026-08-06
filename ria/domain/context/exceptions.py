"""Domain Exceptions for C7 Context Builder."""


class ContextDomainException(Exception):
    """Base exception for all domain errors in Context Builder."""

    pass


class InvalidContextRequestError(ContextDomainException):
    """Raised when context request parameters are malformed."""

    pass


class TokenBudgetExceededError(ContextDomainException):
    """Raised when context building cannot satisfy minimum constraints within token budget."""

    pass
