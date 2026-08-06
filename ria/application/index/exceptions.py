"""Application Exceptions for Index Core."""


class IndexApplicationException(Exception):
    """Base exception for all application-level errors in Index Core."""

    pass


class RepositoryScanException(IndexApplicationException):
    """Raised when repository file discovery or scanning fails."""

    pass


class PipelineException(IndexApplicationException):
    """Raised when IndexPipeline orchestration encounters an unrecoverable failure."""

    pass
