"""Application Exceptions for Search Engine Subsystem."""


class SearchException(Exception):
    """Base exception for Search Engine failures."""

    pass


class SearchIndexException(SearchException):
    """Raised when search index construction or lookup fails."""

    pass


class SearchExecutionException(SearchException):
    """Raised when search query execution fails."""

    pass
