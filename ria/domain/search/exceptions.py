"""Domain Exceptions for C6 Search Engine."""


class SearchDomainException(Exception):
    """Base exception for all domain errors in Search Engine."""

    pass


class InvalidSearchQueryError(SearchDomainException):
    """Raised when search query parameters are malformed."""

    pass


class SearchPlanningError(SearchDomainException):
    """Raised when search plan generation fails."""

    pass
