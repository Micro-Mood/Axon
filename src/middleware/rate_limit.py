"""
Layer 5: Middleware — 限流中间件

职责:
- 限制请求速率，防止客户端过快调用导致资源耗尽
- 三层限流: 全局 → 读写分类 → per-method（可选）
- 滑动窗口算法
- 写操作使用更严格的限流窗口
- 超限抛 RateLimitError（429）

算法: 滑动窗口计数器
- 维护每个窗口（时间段）内的请求计数
- 窗口过期后自动清除
- O(1) 检查 + O(1) 记录

依赖:
- Layer 1: core (RateLimitError)
- Layer 4: handlers/base (RequestContext)
"""

from __future__ import annotations

import logging
import time
from typing import Any

from ..core.errors import RateLimitError
from ..handlers.base import RequestContext
from .chain import NextFunc

logger = logging.getLogger(__name__)


# 写操作方法名 — 使用更严格的限流
# 默认硬编码，可通过构造函数注入 tools 自动派生
_WRITE_METHODS = frozenset({
    "create_file",
    "write_file",
    "replace_range",
    "insert_text",
    "delete_range",
    "apply_patch",
    "move_file",
    "copy_file",
    "delete_file",
    "create_directory",
    "move_directory",
    "delete_directory",
    "set_workspace",
})


class _SlidingWindowCounter:
    """
    滑动窗口计数器

    将时间线按 window_ms 分段，每段记录请求数。
    检查时累加当前段和前一段（按时间比例折算）。

    比简单计数器更平滑，避免窗口边界突刺。
    """

    __slots__ = ("_window_ms", "_max_count", "_prev_count", "_curr_count",
                 "_prev_window", "_curr_window")

    def __init__(self, window_ms: float, max_count: int) -> None:
        self._window_ms = window_ms
        self._max_count = max_count
        self._prev_count = 0
        self._curr_count = 0
        self._prev_window = 0
        self._curr_window = 0

    def _current_window_id(self) -> int:
        """当前时间对应的窗口 ID"""
        return int(time.monotonic() * 1000 / self._window_ms)

    def _rotate(self) -> None:
        """如果窗口已过期，旋转计数"""
        now_window = self._current_window_id()

        if now_window == self._curr_window:
            return  # 仍在当前窗口

        if now_window == self._curr_window + 1:
            # 进入下一个窗口 — 当前变前一个
            self._prev_count = self._curr_count
            self._prev_window = self._curr_window
            self._curr_count = 0
            self._curr_window = now_window
        else:
            # 跳过了多个窗口 — 完全重置
            self._prev_count = 0
            self._prev_window = now_window - 1
            self._curr_count = 0
            self._curr_window = now_window

    def check_and_record(self) -> bool:
        """
        检查是否允许请求，如果允许则记录

        Returns:
            True — 允许（已记录）
            False — 超限（未记录）
        """
        self._rotate()

        # 滑动窗口: 前一窗口按时间比例折算 + 当前窗口完整计数
        now_ms = time.monotonic() * 1000
        elapsed_in_window = now_ms - (self._curr_window * self._window_ms)
        weight = 1.0 - (elapsed_in_window / self._window_ms)
        if weight < 0:
            weight = 0.0

        estimated = self._prev_count * weight + self._curr_count

        if estimated >= self._max_count:
            return False

        self._curr_count += 1
        return True

    @property
    def max_count(self) -> int:
        return self._max_count

    @property
    def window_ms(self) -> float:
        return self._window_ms

    def reset(self) -> None:
        """重置计数器（测试用）"""
        self._prev_count = 0
        self._curr_count = 0
        self._prev_window = 0
        self._curr_window = 0


class RateLimitMiddleware:
    """
    限流中间件

    双层限流:
    1. Global — 所有方法共享的总请求限制
    2. Per-method — 每个方法独立的限制

    写操作自动使用更严格的限流窗口（默认是读操作的 1/5）。

    使用示例:
        rate_limit = RateLimitMiddleware(
            global_rpm=600,          # 全局: 600 次/分钟（10 次/秒）
            read_rpm=300,            # 读操作: 300 次/分钟
            write_rpm=60,            # 写操作: 60 次/分钟
        )
    """

    def __init__(
        self,
        global_rpm: int = 600,
        read_rpm: int = 300,
        write_rpm: int = 60,
        window_ms: float = 60_000.0,
        enabled: bool = True,
        tools: dict | None = None,
    ) -> None:
        """
        Args:
            global_rpm: 全局每分钟请求上限
            read_rpm: 读操作每分钟上限
            write_rpm: 写操作每分钟上限
            window_ms: 滑动窗口大小（毫秒），默认 60 秒
            enabled: 是否启用限流（False 则透传所有请求）
            tools: {name: ToolDef} 字典，传入后自动派生写方法集
        """
        self._enabled = enabled
        self._global_counter = _SlidingWindowCounter(window_ms, global_rpm)
        self._read_counter = _SlidingWindowCounter(window_ms, read_rpm)
        self._write_counter = _SlidingWindowCounter(window_ms, write_rpm)
        # per-method 计数器（通过 set_method_limit 显式注册）
        self._method_counters: dict[str, _SlidingWindowCounter] = {}
        self._default_window_ms = window_ms
        # 从 tools 派生写方法集，未传则回退到内置默认
        if tools is not None:
            self._write_methods = frozenset(
                t.name for t in tools.values() if t.is_write
            )
        else:
            self._write_methods = _WRITE_METHODS

    async def __call__(
        self, ctx: RequestContext, next_handler: NextFunc
    ) -> dict[str, Any]:
        if not self._enabled:
            return await next_handler(ctx)

        method = ctx.method
        is_write = method in self._write_methods

        # ── 1. 全局限流 ──
        if not self._global_counter.check_and_record():
            logger.warning(
                "全局限流触发: method=%s request_id=%s",
                method,
                ctx.request_id,
            )
            raise RateLimitError(
                f"请求过于频繁（全局限制: {self._global_counter.max_count} 次/"
                f"{self._global_counter.window_ms / 1000:.0f}s）",
                details={
                    "method": method,
                    "limit_type": "global",
                    "max_rpm": self._global_counter.max_count,
                },
                suggestion="请降低请求频率后重试",
            )

        # ── 2. 读写分类限流 ──
        if is_write:
            counter = self._write_counter
            limit_type = "write"
        else:
            counter = self._read_counter
            limit_type = "read"

        if not counter.check_and_record():
            logger.warning(
                "%s 限流触发: method=%s request_id=%s",
                limit_type,
                method,
                ctx.request_id,
            )
            raise RateLimitError(
                f"请求过于频繁（{limit_type} 限制: {counter.max_count} 次/"
                f"{counter.window_ms / 1000:.0f}s）",
                details={
                    "method": method,
                    "limit_type": limit_type,
                    "max_rpm": counter.max_count,
                },
                suggestion="请降低请求频率后重试",
            )

        # ── 3. Per-method 限流（仅对显式设置过限制的方法生效）──
        if method in self._method_counters:
            method_counter = self._method_counters[method]
            if not method_counter.check_and_record():
                logger.warning(
                    "per-method 限流触发: method=%s request_id=%s",
                    method,
                    ctx.request_id,
                )
                raise RateLimitError(
                    f"请求过于频繁（方法 '{method}' 限制: {method_counter.max_count} 次/"
                    f"{method_counter.window_ms / 1000:.0f}s）",
                    details={
                        "method": method,
                        "limit_type": "per_method",
                        "max_rpm": method_counter.max_count,
                    },
                    suggestion="请降低请求频率后重试",
                )

        return await next_handler(ctx)

    def set_method_limit(self, method: str, rpm: int) -> None:
        """
        为特定方法设置独立的限流值

        Args:
            method: 方法名
            rpm: 每分钟请求上限
        """
        self._method_counters[method] = _SlidingWindowCounter(
            self._default_window_ms, rpm
        )

    def reset(self) -> None:
        """重置所有计数器（测试用）"""
        self._global_counter.reset()
        self._read_counter.reset()
        self._write_counter.reset()
        for counter in self._method_counters.values():
            counter.reset()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
