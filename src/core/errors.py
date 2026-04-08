"""
Layer 1: Core — 错误与警告体系

异常层级:
    MCPError (base)
    ├── RequestError (4xx 客户端问题)
    │   ├── InvalidParameterError  400
    │   ├── EncodingError          400
    │   ├── PatchApplyError        400
    │   ├── FileNotFoundError      404
    │   ├── TaskNotFoundError      404
    │   ├── PermissionDeniedError  403
    │   ├── BlockedPathError       403
    │   ├── BlockedCommandError    403
    │   ├── PathOutsideWorkspaceError 403
    │   ├── SymlinkError           403
    │   ├── TaskAlreadyRunningError 409
    │   ├── ConcurrentModificationError 409
    │   ├── SizeLimitExceededError 413
    │   ├── MaxConcurrentTasksError 429
    │   └── TimeoutError           408
    └── ServerError (5xx 服务端问题)
        ├── TaskFailedError        500
        ├── ConfigLoadError        500
        └── SystemError            500
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


# ═══════════════════════════════════════════════════════
#  Warning
# ═══════════════════════════════════════════════════════

# 预定义警告码
WARNING_OUTPUT_TRUNCATED = "OUTPUT_TRUNCATED"
WARNING_SLOW_OPERATION = "SLOW_OPERATION"
WARNING_LARGE_FILE = "LARGE_FILE"
WARNING_HIGH_MEMORY = "HIGH_MEMORY"
WARNING_DEPRECATED_METHOD = "DEPRECATED_METHOD"
WARNING_PARTIAL_RESULT = "PARTIAL_RESULT"


@dataclass(frozen=True)
class Warning:
    """请求级别警告，嵌入响应返回给调用方"""

    code: str
    message: str
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {"code": self.code, "message": self.message}
        if self.details:
            d["details"] = self.details
        return d


# ═══════════════════════════════════════════════════════
#  MCPError 基类
# ═══════════════════════════════════════════════════════

class MCPError(Exception):
    """所有 MCP 异常的基类"""

    error_code: str = "MCP_ERROR"
    http_status: int = 500

    def __init__(
        self,
        message: str,
        *,
        details: dict | None = None,
        suggestion: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.suggestion = suggestion
        self.cause = cause
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d: dict = {
            "code": self.error_code,
            "message": self.message,
            "timestamp": self.timestamp,
        }
        if self.details:
            d["details"] = self.details
        if self.suggestion:
            d["suggestion"] = self.suggestion
        if self.cause:
            d["cause"] = str(self.cause)
        return d

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.error_code}: {self.message})"


# ═══════════════════════════════════════════════════════
#  RequestError (4xx) — 客户端/调用方问题
# ═══════════════════════════════════════════════════════

class RequestError(MCPError):
    """调用方问题的基类"""
    error_code = "REQUEST_ERROR"
    http_status = 400


# ── 400 Bad Request ──

class InvalidParameterError(RequestError):
    error_code = "INVALID_PARAMETER"
    http_status = 400


class EncodingError(RequestError):
    error_code = "ENCODING_ERROR"
    http_status = 400


class PatchApplyError(RequestError):
    error_code = "PATCH_APPLY_ERROR"
    http_status = 400


# ── 403 Forbidden ──

class PermissionDeniedError(RequestError):
    error_code = "PERMISSION_DENIED"
    http_status = 403


class BlockedPathError(RequestError):
    error_code = "BLOCKED_PATH"
    http_status = 403


class BlockedCommandError(RequestError):
    error_code = "BLOCKED_COMMAND"
    http_status = 403


class PathOutsideWorkspaceError(RequestError):
    error_code = "PATH_OUTSIDE_WORKSPACE"
    http_status = 403


class SymlinkError(RequestError):
    error_code = "SYMLINK_ERROR"
    http_status = 403


# ── 404 Not Found ──

class FileNotFoundError(RequestError):
    error_code = "FILE_NOT_FOUND"
    http_status = 404


class TaskNotFoundError(RequestError):
    error_code = "TASK_NOT_FOUND"
    http_status = 404


# ── 408 Timeout ──

class TimeoutError(RequestError):
    error_code = "TIMEOUT"
    http_status = 408


# ── 409 Conflict ──

class TaskAlreadyRunningError(RequestError):
    error_code = "TASK_ALREADY_RUNNING"
    http_status = 409


class ConcurrentModificationError(RequestError):
    error_code = "CONCURRENT_MODIFICATION"
    http_status = 409


# ── 413 Payload Too Large ──

class SizeLimitExceededError(RequestError):
    error_code = "SIZE_LIMIT_EXCEEDED"
    http_status = 413


# ── 429 Too Many Requests ──

class MaxConcurrentTasksError(RequestError):
    error_code = "MAX_CONCURRENT_TASKS"
    http_status = 429


class RateLimitError(RequestError):
    error_code = "RATE_LIMIT_EXCEEDED"
    http_status = 429


# ═══════════════════════════════════════════════════════
#  ServerError (5xx) — 服务端问题
# ═══════════════════════════════════════════════════════

class ServerError(MCPError):
    """服务端问题的基类"""
    error_code = "SERVER_ERROR"
    http_status = 500


class TaskFailedError(ServerError):
    error_code = "TASK_FAILED"
    http_status = 500


class ConfigLoadError(ServerError):
    error_code = "CONFIG_LOAD_ERROR"
    http_status = 500


class InternalError(ServerError):
    error_code = "INTERNAL_ERROR"
    http_status = 500
