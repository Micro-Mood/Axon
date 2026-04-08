"""
Layer 4: Handlers — 业务逻辑层

提供:
- BaseHandler: 所有 handler 的基类
- RequestContext: 请求上下文（贯穿中间件和 handler）
- TaskState / Task: 异步任务数据模型
- FileHandler: 文件操作 (16 个方法)
- SearchHandler: 搜索操作 (3 个方法)
- CommandHandler: 命令执行与进程管理 (10 个方法)
- SystemHandler: 系统管理 (7 个方法)

依赖:
- Layer 1: core (Config, Cache, Errors)
- Layer 2: platform (编码、信号、文件系统)
- Layer 3: stream (StreamManager, OutputBuffer)
"""

from .base import BaseHandler, RequestContext, Task, TaskState
from .command import CommandHandler
from .file import FileHandler
from .search import SearchHandler
from .system import SystemHandler

__all__ = [
    # 基础
    "BaseHandler",
    "RequestContext",
    "Task",
    "TaskState",
    # Handlers
    "FileHandler",
    "SearchHandler",
    "CommandHandler",
    "SystemHandler",
]
