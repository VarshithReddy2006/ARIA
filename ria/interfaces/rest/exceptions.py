"""REST API Exception handling."""


class RESTAPIException(Exception):
    """Base exception for REST API layer errors."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class RepositoryNotFoundAPIError(RESTAPIException):
    """Raised when target repository is not found."""

    def __init__(self, repo_id: str) -> None:
        super().__init__(f"Repository '{repo_id}' not found.", status_code=404)


class InvalidQueryAPIError(RESTAPIException):
    """Raised when query format is invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=400)
