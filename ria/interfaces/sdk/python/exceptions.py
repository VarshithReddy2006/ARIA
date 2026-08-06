"""Python SDK Exception Classes."""


class RIASDKException(Exception):
    """Base exception for RIA Python SDK errors."""

    pass


class SDKClientError(RIASDKException):
    """Raised when client request processing fails."""

    pass
