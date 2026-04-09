"""
Layer 1: Core — 基础设施层

提供: 配置、错误、安全校验、缓存、资源追踪、文件锁
无业务逻辑，其他所有层均可依赖此层
"""

from .cache import CacheManager
from .config import (
    ConfigHolder,
    LoggingConfig,
    MCPConfig,
    PerformanceConfig,
    SecurityConfig,
    ServerConfig,
    WorkspaceConfig,
    load_config,
)
from .errors import (
    BlockedCommandError,
    BlockedPathError,
    ConcurrentModificationError,
    ConfigLoadError,
    EncodingError,
    FileNotFoundError,
    InternalError,
    InvalidParameterError,
    MCPError,
    MaxConcurrentTasksError,
    PatchApplyError,
    PathOutsideWorkspaceError,
    PermissionDeniedError,
    RateLimitError,
    RequestError,
    ServerError,
    SizeLimitExceededError,
    SymlinkError,
    TaskAlreadyRunningError,
    TaskFailedError,
    TaskNotFoundError,
    TimeoutError,
    Warning,
)
from .filelock import AsyncFileLockManager
from .resource import ResourceTracker
from .security import SecurityChecker

__all__ = [
    # Config
    "MCPConfig",
    "WorkspaceConfig",
    "SecurityConfig",
    "PerformanceConfig",
    "LoggingConfig",
    "ServerConfig",
    "ConfigHolder",
    "load_config",
    # Errors
    "MCPError",
    "RequestError",
    "ServerError",
    "InvalidParameterError",
    "EncodingError",
    "PatchApplyError",
    "FileNotFoundError",
    "TaskNotFoundError",
    "PermissionDeniedError",
    "BlockedPathError",
    "BlockedCommandError",
    "PathOutsideWorkspaceError",
    "SymlinkError",
    "TaskAlreadyRunningError",
    "ConcurrentModificationError",
    "SizeLimitExceededError",
    "MaxConcurrentTasksError",
    "RateLimitError",
    "TimeoutError",
    "TaskFailedError",
    "ConfigLoadError",
    "InternalError",
    "Warning",
    # Security
    "SecurityChecker",
    # Cache
    "CacheManager",
    # Resource
    "ResourceTracker",
    # FileLock
    "AsyncFileLockManager",
]
