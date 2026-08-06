"""Domain Exceptions for C4 Query Engine."""


class QueryDomainException(Exception):
    """Base exception for all domain errors in Query Engine."""

    pass


class InvalidQueryCriteriaError(QueryDomainException):
    """Raised when query criteria parameters are malformed."""

    pass


class QueryPlanningError(QueryDomainException):
    """Raised when query plan generation fails."""

    pass
