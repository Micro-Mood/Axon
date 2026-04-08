"""
Layer 4: Handlers — 基类与公共数据模型

提供:
- RequestContext: 请求上下文，贯穿中间件链和 handler
- TaskState / Task: 异步任务数据模型
- BaseHandler: 所有 handler 的基类

依赖:
- Layer 1: core (MCPConfig, CacheManager, Warning)
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from ..core.config import MCPConfig
from ..core.cache import CacheManager
from ..core.errors import Warning


# ═══════════════════════════════════════════════════════
#  RequestContext — 请求上下文
# ═══════════════════════════════════════════════════════

@dataclass
class RequestContext:
    """
    每个请求一个实例，贯穿中间件链和 handler

    用途:
    - 携带请求元数据（method, params, request_id）
    - 中间件写入校验后的路径（validated_paths）
    - handler/middleware 追加警告（warnings）
    """

    method: str
    params: dict[str, Any]
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    # 中间件写入
    validated_paths: dict[str, Path] = field(default_factory=dict)
    # 警告收集
    warnings: list[Warning] = field(default_factory=list)

    def warn(self, code: str, message: str, **details: Any) -> None:
        """追加一条警告"""
        self.warnings.append(Warning(code=code, message=message, details=details))


# ═══════════════════════════════════════════════════════
#  TaskState & Task — 异步任务数据模型
# ═══════════════════════════════════════════════════════

class TaskState(Enum):
    """任务生命周期状态"""
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"     # 优雅停止
    KILLED = "killed"       # 强制终止
    TIMED_OUT = "timed_out" # 超时终止


@dataclass
class Task:
    """
    一个异步命令执行任务

    状态转移:
        CREATED → RUNNING → COMPLETED (exit_code==0)
                         → FAILED    (exit_code!=0)
                         → STOPPED   (stop())
                         → KILLED    (kill())
                         → TIMED_OUT (超时)
    """

    task_id: str
    command: str
    cwd: str | None
    env: dict[str, str] | None
    state: TaskState
    process: asyncio.subprocess.Process | None

    pid: int | None = None
    exit_code: int | None = None
    signal: str | None = None

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def duration_ms(self) -> float | None:
        """任务运行时长（毫秒），未完成返回 None"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds() * 1000
        return None

    @property
    def is_active(self) -> bool:
        """任务是否还在活跃（可被操作）"""
        return self.state in (TaskState.CREATED, TaskState.RUNNING)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典（排除 process 对象）"""
        return {
            "task_id": self.task_id,
            "command": self.command,
            "cwd": self.cwd,
            "state": self.state.value,
            "pid": self.pid,
            "exit_code": self.exit_code,
            "signal": self.signal,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
        }


# ═══════════════════════════════════════════════════════
#  BaseHandler — handler 基类
# ═══════════════════════════════════════════════════════

class BaseHandler:
    """
    所有 handler 的基类

    通过构造函数注入依赖（不使用全局单例）:
    - config: 全局配置
    - cache: 缓存管理器
    """

    def __init__(self, config: MCPConfig, cache: CacheManager):
        self.config = config
        self.cache = cache

    @property
    def workspace(self) -> Path:
        """便捷访问: 工作区根路径（已解析为绝对路径）"""
        return self.config.workspace.root
