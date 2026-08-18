"""Public API error types."""

from __future__ import annotations


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


class InvalidRequestError(AppError):
    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(400, code, message, details)


class ResultNotReadyError(AppError):
    def __init__(self, resource: str = "analysis result"):
        super().__init__(
            503,
            "RESULT_NOT_READY",
            f"The {resource} has not been published yet.",
        )


class UpstreamServiceError(AppError):
    def __init__(self, message: str = "The AI service is temporarily unavailable."):
        super().__init__(503, "UPSTREAM_SERVICE_ERROR", message)


class DatabaseUnavailableError(AppError):
    def __init__(self):
        super().__init__(
            503,
            "DATABASE_UNAVAILABLE",
            "The data service is temporarily unavailable.",
        )


class ServerMisconfiguredError(AppError):
    def __init__(self):
        super().__init__(
            500,
            "SERVER_MISCONFIGURED",
            "The service configuration is incomplete.",
        )


class InvalidServiceResultError(AppError):
    def __init__(self):
        super().__init__(
            500,
            "SERVICE_RESULT_INVALID",
            "The published service result failed validation.",
        )
