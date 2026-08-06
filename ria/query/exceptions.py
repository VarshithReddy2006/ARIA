"""Application Exceptions for C4 Query Engine."""


class QueryException(Exception):
    """Base exception for all Query Engine errors."""

    pass


class DefinitionNotFoundException(QueryException):
    """Raised when symbol definition lookup fails."""

    pass


class ReferenceNotFoundException(QueryException):
    """Raised when symbol reference lookup fails."""

    pass


class DependencyResolutionException(QueryException):
    """Raised when module dependency analysis fails."""

    pass


class QueryExecutionException(QueryException):
    """Raised when query execution encounters an unexpected failure."""

    pass
