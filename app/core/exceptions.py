from typing import Any, Optional


class MiddleServiceException(Exception):
    """Base exception for all domain and service errors."""

    def __init__(self, message: str, details: Optional[Any] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class ResourceNotFoundException(MiddleServiceException):
    """Raised when an entity is not found in database."""

    pass


class ResourceConflictException(MiddleServiceException):
    """Raised on scheduling conflicts, duplicate keys, etc."""

    pass


class NuveqApiError(MiddleServiceException):
    """Raised when upstream Nuveq API returns an error or is unreachable."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        nuveq_response: Optional[Any] = None,
    ) -> None:
        super().__init__(message, details=nuveq_response)
        self.status_code = status_code
        self.nuveq_response = nuveq_response


class InvalidWebhookSecretException(MiddleServiceException):
    """Raised when an incoming webhook provides an invalid secret token."""

    pass


class UnauthorizedClientException(MiddleServiceException):
    """Raised when client API key is missing or invalid."""

    pass
