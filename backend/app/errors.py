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
            f"{resource}尚未发布。",
        )

class UpstreamServiceError(AppError):
    def __init__(self, message: str = "AI 服务暂时不可用，请稍后重试。"):
        super().__init__(503, "UPSTREAM_SERVICE_ERROR", message)

class DatabaseUnavailableError(AppError):
    def __init__(self):
        super().__init__(
            503,
            "DATABASE_UNAVAILABLE",
            "数据服务暂时不可用，请检查数据库连接。",
        )


class ServerMisconfiguredError(AppError):
    def __init__(self):
        super().__init__(
            500,
            "SERVER_MISCONFIGURED",
            "服务配置不完整，请检查后端环境变量。",
        )


class InvalidServiceResultError(AppError):
    def __init__(self):
        super().__init__(
            500,
            "SERVICE_RESULT_INVALID",
            "已发布服务结果校验失败。",
        )
