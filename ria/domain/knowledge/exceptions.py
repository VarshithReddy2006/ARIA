"""Domain Exceptions for C8 Knowledge Layer."""


class KnowledgeDomainException(Exception):
    """Base exception for all domain errors in Knowledge Layer."""

    pass


class InvalidKnowledgeRequestError(KnowledgeDomainException):
    """Raised when a knowledge request is malformed."""

    pass


class ProviderExecutionError(KnowledgeDomainException):
    """Raised when LLM provider invocation fails."""

    pass


class ResponseValidationError(KnowledgeDomainException):
    """Raised when generated response fails grounding validation."""

    pass
