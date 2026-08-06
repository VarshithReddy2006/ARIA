"""Domain Exceptions for C1 Index Core."""


class IndexingDomainException(Exception):
    """Base exception for all domain errors in Index Core."""

    pass


class UnsupportedLanguageError(IndexingDomainException):
    """Raised when a file's language is not supported by any active parser plugin."""

    pass


class FileTooLargeError(IndexingDomainException):
    """Raised when a file exceeds the maximum indexable size limit."""

    pass


class InvalidASTError(IndexingDomainException):
    """Raised when an AST structure is corrupted or invalid."""

    pass
