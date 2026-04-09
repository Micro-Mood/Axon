"""
Layer 1: Core — 资源追踪器

职责:
- 任务并发控制（最大同时运行任务数）
- 内存配额追踪（防止单个连接/操作耗尽内存）
- 资源统计快照（供 get_stats / 监控使用）

设计:
- 纯异步，所有状态修改通过 asyncio.Lock 串行化
- 无 I/O，不依赖 psutil 等外部包
- 与 SecurityChecker 平级，都是 Layer 1 无状态工具
  （ResourceTracker 有状态，但只是计数器，不做业务决策）

依赖:
- config.PerformanceConfig (限制值)
- errors (MaxConcurrentTasksError)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .config import PerformanceConfig
from .errors import MaxConcurrentTasksError


@dataclass(frozen=True)
class ResourceSnapshot:
    """资源状态快照（不可变，线程安全）"""

    active_tasks: int
    max_tasks: int
    tracked_memory_bytes: int
    max_memory_bytes: int
    timestamp: str

    @property
    def task_utilization(self) -> float:
        """任务槽利用率 (0.0~1.0)"""
        return self.active_tasks / self.max_tasks if self.max_tasks > 0 else 0.0

    @property
    def memory_utilization(self) -> float:
        """内存配额利用率 (0.0~1.0)"""
        return (
            self.tracked_memory_bytes / self.max_memory_bytes
            if self.max_memory_bytes > 0
            else 0.0
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_tasks": self.active_tasks,
            "max_tasks": self.max_tasks,
            "task_utilization": round(self.task_utilization, 3),
            "tracked_memory_mb": round(self.tracked_memory_bytes / (1024 * 1024), 2),
            "max_memory_mb": round(self.max_memory_bytes / (1024 * 1024), 2),
            "memory_utilization": round(self.memory_utilization, 3),
            "timestamp": self.timestamp,
        }


class ResourceTracker:
    """
    异步资源追踪器

    两个维度:
    1. 任务并发: register_task / unregister_task
       超过 max_concurrent_tasks 时抛 MaxConcurrentTasksError

    2. 内存配额: track_memory / release_memory
       追踪累积内存分配，超过 max_output_buffer_mb 时抛异常
       （这是逻辑配额，不是物理内存监控）

    用法::

        tracker = ResourceTracker(config.performance)

        # 任务注册
        await tracker.register_task("task-001")
        try:
            ...  # 执行任务
        finally:
            await tracker.unregister_task("task-001")

        # 内存追踪
        await tracker.track_memory(1024 * 1024)  # 申请 1MB
        try:
            ...  # 使用内存
        finally:
            await tracker.release_memory(1024 * 1024)
    """

    def __init__(self, config: PerformanceConfig) -> None:
        self._max_tasks = config.max_concurrent_tasks
        self._max_memory_bytes = config.max_output_buffer_mb * 1024 * 1024

        self._active_tasks: set[str] = set()
        self._tracked_memory: int = 0
        self._lock = asyncio.Lock()

        # 统计计数器
        self._total_registered: int = 0
        self._total_rejected: int = 0

    # ── 任务并发控制 ──

    async def register_task(self, task_id: str) -> None:
        """
        注册新任务

        如果活动任务数已达上限，抛出 MaxConcurrentTasksError。
        重复注册同一 task_id 是幂等的（不计数）。

        Args:
            task_id: 唯一任务标识

        Raises:
            MaxConcurrentTasksError: 超过并发上限
        """
        async with self._lock:
            # 幂等: 已注册的不重复计
            if task_id in self._active_tasks:
                return

            if len(self._active_tasks) >= self._max_tasks:
                self._total_rejected += 1
                raise MaxConcurrentTasksError(
                    f"已达最大并发任务数: {self._max_tasks}",
                    details={
                        "active_tasks": len(self._active_tasks),
                        "max_tasks": self._max_tasks,
                        "task_id": task_id,
                    },
                    suggestion="等待现有任务完成后再创建新任务",
                )

            self._active_tasks.add(task_id)
            self._total_registered += 1

    async def unregister_task(self, task_id: str) -> None:
        """
        注销任务

        幂等: 注销不存在的 task_id 不报错。
        """
        async with self._lock:
            self._active_tasks.discard(task_id)

    @property
    def active_task_count(self) -> int:
        """当前活动任务数（无锁读，允许轻微不一致）"""
        return len(self._active_tasks)

    @property
    def active_task_ids(self) -> frozenset[str]:
        """当前活动任务 ID 集合"""
        return frozenset(self._active_tasks)

    # ── 内存配额追踪 ──

    async def track_memory(self, size_bytes: int) -> None:
        """
        申请内存配额

        如果累积已追踪内存 + size_bytes 超过 max_output_buffer_mb，
        抛出 MaxConcurrentTasksError（复用 429 语义: 资源不足）。

        Args:
            size_bytes: 申请的字节数

        Raises:
            MaxConcurrentTasksError: 超过内存配额
        """
        if size_bytes <= 0:
            return

        async with self._lock:
            new_total = self._tracked_memory + size_bytes
            if new_total > self._max_memory_bytes:
                raise MaxConcurrentTasksError(
                    f"内存配额超限: 已用 {self._tracked_memory / (1024*1024):.1f}MB + "
                    f"请求 {size_bytes / (1024*1024):.1f}MB > "
                    f"上限 {self._max_memory_bytes / (1024*1024):.1f}MB",
                    details={
                        "tracked_mb": round(self._tracked_memory / (1024 * 1024), 2),
                        "requested_mb": round(size_bytes / (1024 * 1024), 2),
                        "max_mb": round(self._max_memory_bytes / (1024 * 1024), 2),
                    },
                    suggestion="等待现有操作释放内存后重试",
                )
            self._tracked_memory = new_total

    async def release_memory(self, size_bytes: int) -> None:
        """
        释放内存配额

        释放量超过已追踪量时，归零而非变负。
        """
        if size_bytes <= 0:
            return

        async with self._lock:
            self._tracked_memory = max(0, self._tracked_memory - size_bytes)

    @property
    def tracked_memory_bytes(self) -> int:
        """当前已追踪内存字节数"""
        return self._tracked_memory

    # ── 快照 & 统计 ──

    def snapshot(self) -> ResourceSnapshot:
        """生成当前资源状态快照"""
        return ResourceSnapshot(
            active_tasks=len(self._active_tasks),
            max_tasks=self._max_tasks,
            tracked_memory_bytes=self._tracked_memory,
            max_memory_bytes=self._max_memory_bytes,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def stats(self) -> dict[str, Any]:
        """统计信息（含历史计数器）"""
        snap = self.snapshot()
        return {
            **snap.to_dict(),
            "total_registered": self._total_registered,
            "total_rejected": self._total_rejected,
        }

    async def reset(self) -> None:
        """重置所有状态（测试用）"""
        async with self._lock:
            self._active_tasks.clear()
            self._tracked_memory = 0
            self._total_registered = 0
            self._total_rejected = 0
