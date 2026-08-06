"""Application Exceptions for Semantic Resolution Engine."""


class ResolutionException(Exception):
    """Base exception for all resolution engine errors."""

    pass


class DefinitionResolutionException(ResolutionException):
    """Raised when symbol definition resolution fails."""

    pass


class ReferenceResolutionException(ResolutionException):
    """Raised when symbol reference resolution fails."""

    pass


class ImportResolutionException(ResolutionException):
    """Raised when import statement resolution fails."""

    pass


class CallResolutionException(ResolutionException):
    """Raised when function/method call resolution fails."""

    pass


class InheritanceResolutionException(ResolutionException):
    """Raised when superclass/interface inheritance resolution fails."""

    pass
