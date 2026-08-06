"""Application Exceptions for Knowledge Subsystem."""


class KnowledgeException(Exception):
    """Base exception for Knowledge Subsystem errors."""

    pass


class IntentAnalysisException(KnowledgeException):
    """Raised when intent classification fails."""

    pass


class PromptBuildingException(KnowledgeException):
    """Raised when prompt generation fails."""

    pass


class ProviderNotFoundException(KnowledgeException):
    """Raised when specified LLM provider is not registered."""

    pass
