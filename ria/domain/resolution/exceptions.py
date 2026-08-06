"""Domain Exceptions for C2 Semantic Resolution Engine."""


class ResolutionDomainException(Exception):
    """Base exception for all domain errors in Semantic Resolution."""

    pass


class InvalidMonikerError(ResolutionDomainException):
    """Raised when a symbol moniker is ill-formed."""

    pass


class InvalidQualifiedNameError(ResolutionDomainException):
    """Raised when a qualified symbol name is invalid."""

    pass


class ScopeResolutionError(ResolutionDomainException):
    """Raised when a symbol scope resolution fails."""

    pass
