"""
Tools — 插件式工具注册表

每个子目录 = 一个 handler 域（file / search / command / system）
每个 .py 文件 = 一个 tool（定义元数据 + execute 函数）

中间件和 server 从这里读取所有元数据，不再硬编码方法名。
新增/删除 tool = 新增/删除一个 .py 文件，其他全自动。

用法:
    from src.tools import discover_all, ToolDef

    all_tools = discover_all()   # {name: ToolDef}
    write_methods = {t.name for t in all_tools.values() if t.is_write}
"""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
#  类型常量（和 validation.py 共享）
# ═══════════════════════════════════════════════════════

STR = "str"
INT = "int"
FLOAT = "float"
BOOL = "bool"
DICT = "dict"
LIST = "list"
STR_OR_NONE = "str|None"
INT_OR_NONE = "int|None"
FLOAT_OR_NONE = "float|None"
BOOL_OR_NONE = "bool|None"
DICT_OR_NONE = "dict|None"
LIST_OR_NONE = "list|None"
TUPLE_INT_INT_OR_NONE = "tuple[int,int]|None"
PATH = STR              # 路径参数（validation 层按 str 校验，router 层做 str→Path 转换）
PATH_OR_NONE = STR_OR_NONE


# ═══════════════════════════════════════════════════════
#  参数定义
# ═══════════════════════════════════════════════════════

@dataclass(slots=True)
class Param:
    """参数定义"""
    name: str
    type: str = STR
    required: bool = True
    default: Any = None
    min_value: int | float | None = None
    max_value: int | float | None = None
    non_empty: bool = False


def param(
    name: str,
    type: str = STR,
    *,
    required: bool = True,
    default: Any = None,
    min_value: int | float | None = None,
    max_value: int | float | None = None,
    non_empty: bool = False,
) -> Param:
    """快捷构建参数定义"""
    return Param(
        name=name, type=type, required=required, default=default,
        min_value=min_value, max_value=max_value, non_empty=non_empty,
    )


# ═══════════════════════════════════════════════════════
#  ToolDef — 工具定义
# ═══════════════════════════════════════════════════════

# execute 函数签名: async def execute(handler, ctx, **kwargs) -> dict
ExecuteFunc = Callable[..., Awaitable[dict[str, Any]]]


@dataclass
class ToolDef:
    """
    一个 tool 的完整元数据

    Attributes:
        name: JSON-RPC 方法名（如 "read_file"）
        description: 工具描述
        lock: 文件锁类型
            "none"       — 不加锁
            "read"       — 共享读锁（path 参数）
            "write"      — 排他写锁（path 参数）
            "write_dual" — 双路径排他锁（source + dest）
            "dir_write"  — 目录排他锁（path 参数）
        track: 任务追踪类型
            None          — 不追踪
            "task_create" — 注册任务到 ResourceTracker
            "task_end"    — 从 ResourceTracker 注销任务
        is_write: 是否为写操作（影响安全校验和限流）
        params: 参数定义列表
        execute: execute 函数引用（由 discover 自动填充）
        group: handler 域名（"file" / "search" 等，由 discover 自动填充）
    """
    name: str
    description: str = ""
    lock: str = "none"
    track: str | None = None
    is_write: bool = False
    params: list[Param] = field(default_factory=list)
    # 以下由 discover 自动填充
    execute: ExecuteFunc | None = field(default=None, repr=False)
    group: str = ""


# ═══════════════════════════════════════════════════════
#  发现与加载
# ═══════════════════════════════════════════════════════

def load_tools_from_package(package: Any) -> list[ToolDef]:
    """
    扫描一个 handler 子包，加载所有 tool 定义

    规则:
    - 遍历包内所有非 __init__ 的 .py 模块
    - 每个模块必须有 `tool` (ToolDef) 和 `execute` (async function) 属性
    - 自动填充 tool.execute 和 tool.group

    Args:
        package: handler 子包（如 src.tools.file）

    Returns:
        该包下所有 ToolDef 列表
    """
    tools: list[ToolDef] = []
    group = package.__name__.rsplit(".", 1)[-1]  # "file", "search", etc.
    pkg_path = package.__path__

    for finder, module_name, is_pkg in pkgutil.iter_modules(pkg_path):
        if module_name.startswith("_"):
            continue  # 跳过 __init__ 和私有模块

        fqn = f"{package.__name__}.{module_name}"
        try:
            mod = importlib.import_module(fqn)
        except Exception:
            logger.exception("加载 tool 模块失败: %s", fqn)
            continue

        tool_def = getattr(mod, "tool", None)
        execute_fn = getattr(mod, "execute", None)

        if not isinstance(tool_def, ToolDef):
            logger.warning("模块 %s 缺少 tool: ToolDef 定义，跳过", fqn)
            continue
        if execute_fn is None or not inspect.iscoroutinefunction(execute_fn):
            logger.warning("模块 %s 缺少 async execute 函数，跳过", fqn)
            continue

        tool_def.execute = execute_fn
        tool_def.group = group
        tools.append(tool_def)

    return tools


def discover_all() -> dict[str, ToolDef]:
    """
    扫描所有 handler 子包，返回全部 tool 定义

    Returns:
        {method_name: ToolDef} 字典
    """
    from . import file, search, command, system

    all_tools: dict[str, ToolDef] = {}

    for package in [file, search, command, system]:
        for tool_def in load_tools_from_package(package):
            if tool_def.name in all_tools:
                logger.warning(
                    "tool 名称冲突: %s（在 %s 和 %s 中重复定义）",
                    tool_def.name, all_tools[tool_def.name].group, tool_def.group,
                )
            all_tools[tool_def.name] = tool_def

    logger.info("已发现 %d 个 tools", len(all_tools))
    return all_tools


# ═══════════════════════════════════════════════════════
#  查询辅助
# ═══════════════════════════════════════════════════════

def methods_by_lock(tools: dict[str, ToolDef], *lock_types: str) -> frozenset[str]:
    """按 lock 类型过滤方法名"""
    return frozenset(t.name for t in tools.values() if t.lock in lock_types)


def write_methods(tools: dict[str, ToolDef]) -> frozenset[str]:
    """所有写操作方法名"""
    return frozenset(t.name for t in tools.values() if t.is_write)


def track_methods(tools: dict[str, ToolDef], track_type: str) -> frozenset[str]:
    """按 track 类型过滤方法名"""
    return frozenset(t.name for t in tools.values() if t.track == track_type)


def get_params(tools: dict[str, ToolDef]) -> dict[str, list[Param]]:
    """获取所有方法的参数 schema"""
    return {name: t.params for name, t in tools.items()}


__all__ = [
    # 数据类型
    "ToolDef", "Param", "ExecuteFunc",
    # 构建
    "param",
    # 类型常量
    "STR", "INT", "FLOAT", "BOOL", "DICT", "LIST",
    "STR_OR_NONE", "INT_OR_NONE", "FLOAT_OR_NONE", "BOOL_OR_NONE",
    "DICT_OR_NONE", "LIST_OR_NONE", "TUPLE_INT_INT_OR_NONE",
    "PATH", "PATH_OR_NONE",
    # 发现
    "discover_all", "load_tools_from_package",
    # 查询
    "methods_by_lock", "write_methods", "track_methods", "get_params",
]
