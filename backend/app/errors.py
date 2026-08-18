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
    def __init__(self):
        super().__init__(
            503,
            "RESULT_NOT_READY",
            "The disease TOP10 result has not been published yet.",
        )


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
