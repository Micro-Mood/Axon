"""
Layer 5: Middleware — 并发控制中间件

职责:
- 写操作自动获取文件排他锁，防止并发写冲突
- 读操作自动获取文件共享锁，与写操作互斥
- 任务创建自动注册到 ResourceTracker 并发控制
- 任务完成后自动注销

方法分类来源:
- 优先使用 tools 插件系统的 ToolDef.lock / ToolDef.track 元数据
- 备选使用内置默认集合（向后兼容）

架构位置:
    Security → Validation → RateLimit → **Concurrency** → [Handler] → Audit
    在限流之后、handler 之前，保证进入 handler 的请求不会并发冲突。

依赖:
- Layer 1: core (AsyncFileLockManager, ResourceTracker)
- Layer 4: handlers/base (RequestContext)
"""

from __future__ import annotations

import logging
from typing import Any

from ..core.filelock import AsyncFileLockManager
from ..core.resource import ResourceTracker
from ..handlers.base import RequestContext
from .chain import NextFunc

logger = logging.getLogger(__name__)


# ── 方法分类（内置默认，可被 tools 覆盖）──

# 文件写操作 — 需要对目标路径加排他锁
_FILE_WRITE_METHODS = frozenset({
    "create_file",
    "write_file",
    "replace_range",
    "insert_text",
    "delete_range",
    "apply_patch",
    "delete_file",
})

# 文件移动/复制 — 需要对 source 和 dest 都加锁
_FILE_MOVE_METHODS = frozenset({
    "move_file",
    "copy_file",
})

# 目录写操作 — 需要对路径加排他锁
_DIR_WRITE_METHODS = frozenset({
    "create_directory",
    "delete_directory",
    "move_directory",
})

# 文件读操作 — 加共享锁
_FILE_READ_METHODS = frozenset({
    "read_file",
    "stat_path",
    "exists",
})

# 任务创建方法 — 需要注册到 ResourceTracker
_TASK_CREATE_METHODS = frozenset({
    "create_task",
})

# 任务结束方法 — 从 ResourceTracker 注销
_TASK_END_METHODS = frozenset({
    "stop_task",
    "kill_task",
})

# 所有需要文件排他锁的方法
_ALL_WRITE_METHODS = _FILE_WRITE_METHODS | _FILE_MOVE_METHODS | _DIR_WRITE_METHODS


def _build_method_sets(tools: dict) -> dict[str, frozenset[str]]:
    """从 tools 插件系统的 ToolDef 元数据派生方法分类集合"""
    file_write = set()
    file_move = set()
    dir_write = set()
    file_read = set()
    task_create = set()
    task_end = set()

    for t in tools.values():
        if t.lock == "write":
            file_write.add(t.name)
        elif t.lock == "write_dual":
            file_move.add(t.name)
        elif t.lock == "dir_write":
            dir_write.add(t.name)
        elif t.lock == "read":
            file_read.add(t.name)

        if t.track == "task_create":
            task_create.add(t.name)
        elif t.track == "task_end":
            task_end.add(t.name)

    return {
        "file_write": frozenset(file_write),
        "file_move": frozenset(file_move),
        "dir_write": frozenset(dir_write),
        "file_read": frozenset(file_read),
        "task_create": frozenset(task_create),
        "task_end": frozenset(task_end),
        "all_write": frozenset(file_write | file_move | dir_write),
    }


class ConcurrencyMiddleware:
    """
    并发控制中间件

    两个维度:
    1. 文件锁: 对文件读写操作自动加共享/排他锁
       - 写操作: path/dest 加排他锁
       - 移动/复制: source + dest 都加排他锁
       - 读操作: path 加共享锁
       → 防止同一文件同时被读写导致不一致

    2. 任务并发: create_task 时注册到 ResourceTracker
       - 超过 max_concurrent_tasks 时拒绝
       - stop_task/kill_task 时注销
       → 防止任务占满系统资源

    两个维度独立，可以只启用其中一个（构造参数控制）。
    """

    def __init__(
        self,
        file_lock_manager: AsyncFileLockManager | None = None,
        resource_tracker: ResourceTracker | None = None,
        tools: dict | None = None,
    ) -> None:
        """
        Args:
            file_lock_manager: 文件锁管理器。None 则不启用文件锁。
            resource_tracker: 资源追踪器。None 则不启用任务并发控制。
            tools: {name: ToolDef} 字典，传入后自动派生方法分类。
        """
        self._file_locks = file_lock_manager
        self._resource_tracker = resource_tracker

        # 从 tools 派生方法分类，未传则回退到内置默认
        if tools is not None:
            sets = _build_method_sets(tools)
            self._file_write = sets["file_write"]
            self._file_move = sets["file_move"]
            self._dir_write = sets["dir_write"]
            self._file_read = sets["file_read"]
            self._task_create = sets["task_create"]
            self._task_end = sets["task_end"]
            self._all_write = sets["all_write"]
        else:
            self._file_write = _FILE_WRITE_METHODS
            self._file_move = _FILE_MOVE_METHODS
            self._dir_write = _DIR_WRITE_METHODS
            self._file_read = _FILE_READ_METHODS
            self._task_create = _TASK_CREATE_METHODS
            self._task_end = _TASK_END_METHODS
            self._all_write = _ALL_WRITE_METHODS

    async def __call__(
        self, ctx: RequestContext, next_handler: NextFunc
    ) -> dict[str, Any]:
        method = ctx.method

        # ── 文件排他锁 ──
        if self._file_locks is not None and method in self._all_write:
            return await self._with_write_lock(ctx, next_handler)

        # ── 文件共享锁 ──
        if self._file_locks is not None and method in self._file_read:
            return await self._with_read_lock(ctx, next_handler)

        # ── 任务并发控制 ──
        if self._resource_tracker is not None and method in self._task_create:
            return await self._with_task_tracking(ctx, next_handler)

        # ── 任务结束 → 注销 ──
        if self._resource_tracker is not None and method in self._task_end:
            return await self._with_task_unregister(ctx, next_handler)

        # 其他方法直接透传
        return await next_handler(ctx)

    async def _with_write_lock(
        self, ctx: RequestContext, next_handler: NextFunc
    ) -> dict[str, Any]:
        """写操作: 获取排他锁 → 执行 → 释放"""
        assert self._file_locks is not None
        method = ctx.method
        params = ctx.params

        if method in self._file_move:
            # 移动/复制: 对 source 和 dest 都加排他锁
            # 按路径排序加锁，避免死锁（A 锁 src→dst，B 锁 dst→src）
            source = params.get("source", "")
            dest = params.get("dest", "")
            paths = sorted([source, dest]) if source and dest else [p for p in [source, dest] if p]

            if len(paths) == 2:
                async with self._file_locks.write_lock(paths[0]):
                    async with self._file_locks.write_lock(paths[1]):
                        return await next_handler(ctx)
            elif len(paths) == 1:
                async with self._file_locks.write_lock(paths[0]):
                    return await next_handler(ctx)
            else:
                return await next_handler(ctx)
        else:
            # 单路径写操作
            path = params.get("path", "")
            if path:
                async with self._file_locks.write_lock(path):
                    return await next_handler(ctx)
            return await next_handler(ctx)

    async def _with_read_lock(
        self, ctx: RequestContext, next_handler: NextFunc
    ) -> dict[str, Any]:
        """读操作: 获取共享锁 → 执行 → 释放"""
        assert self._file_locks is not None
        path = ctx.params.get("path", "")
        if path:
            async with self._file_locks.read_lock(path):
                return await next_handler(ctx)
        return await next_handler(ctx)

    async def _with_task_tracking(
        self, ctx: RequestContext, next_handler: NextFunc
    ) -> dict[str, Any]:
        """
        任务创建: 预注册 → 执行 → 成功保留 / 失败注销

        task_id 从 handler 返回的 result 中提取。
        注册使用临时 ID（request_id），handler 成功后替换为真实 task_id。
        """
        assert self._resource_tracker is not None

        temp_id = f"pending-{ctx.request_id}"
        await self._resource_tracker.register_task(temp_id)

        try:
            result = await next_handler(ctx)
        except BaseException:
            # handler 失败 → 释放预注册的槽位
            await self._resource_tracker.unregister_task(temp_id)
            raise

        # handler 成功 → 用真实 task_id 替换临时 ID
        # 先注册真实 ID 再注销临时 ID，保证槽位不被抢占
        real_task_id = None
        if isinstance(result, dict):
            data = result.get("data", result)
            real_task_id = data.get("task_id")

        if real_task_id:
            # 先注册真实 ID（幂等，不会多占槽位因为 temp_id 还在）
            # 但需要临时放宽一个槽位来容纳两个 ID 共存
            # 更简洁的做法: 直接替换 set 内容
            async with self._resource_tracker._lock:
                self._resource_tracker._active_tasks.discard(temp_id)
                self._resource_tracker._active_tasks.add(real_task_id)
        else:
            await self._resource_tracker.unregister_task(temp_id)

        return result

    async def _with_task_unregister(
        self, ctx: RequestContext, next_handler: NextFunc
    ) -> dict[str, Any]:
        """
        任务结束: 先执行 handler → 成功后注销 task_id

        task_id 从 params 中提取（stop_task/kill_task 需要指定目标）。
        """
        assert self._resource_tracker is not None

        result = await next_handler(ctx)

        # handler 成功 → 注销 task_id
        task_id = ctx.params.get("task_id", "")
        if task_id:
            await self._resource_tracker.unregister_task(task_id)
            logger.debug("任务注销: task_id=%s method=%s", task_id, ctx.method)

        return result
