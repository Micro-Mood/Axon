"""
Layer 5: Middleware — 审计日志中间件

职责:
- 记录每个请求的方法名、耗时、结果状态
- 慢操作自动追加 WARNING_SLOW_OPERATION 警告
- 异常情况记录错误日志（但不吞没异常，继续上浮）
- 记录操作轨迹（what, when, how long, success/fail）

架构:
    AuditMiddleware 应注册在最后一个（最靠近 handler），
    这样它测量的是 handler 执行时间（不含前置中间件开销）。
    但在洋葱模型中，它包裹 handler，所以后置处理能拿到结果。

    如果需要测量完整链路耗时，可以额外在最外层放一个
    TimingMiddleware。但通常 ctx.duration_ms 就够了。

依赖:
- Layer 1: core (WARNING_SLOW_OPERATION, MCPError)
- Layer 4: handlers/base (RequestContext)
"""

from __future__ import annotations

import logging
from typing import Any

from ..core.errors import MCPError, WARNING_SLOW_OPERATION
from ..handlers.base import RequestContext
from .chain import NextFunc

logger = logging.getLogger(__name__)


class AuditMiddleware:
    """
    审计日志 + 慢操作警告

    每次请求完成（成功或失败）都会记录一条结构化日志:
    - method: 方法名
    - request_id: 请求 ID
    - duration_ms: 耗时
    - status: success / error
    - warnings_count: 警告数
    - error_code: 错误码（仅失败时）

    慢操作阈值可通过构造函数配置。
    """

    def __init__(
        self,
        slow_threshold_ms: float = 5000.0,
        log_params: bool = False,
    ) -> None:
        """
        Args:
            slow_threshold_ms: 超过此阈值（毫秒）的操作会追加慢操作警告
            log_params: 是否在日志中记录请求参数（debug 用，
                        生产环境应关闭以避免记录敏感数据）
        """
        self._slow_threshold_ms = slow_threshold_ms
        self._log_params = log_params

    async def __call__(
        self, ctx: RequestContext, next_handler: NextFunc
    ) -> dict[str, Any]:
        method = ctx.method
        request_id = ctx.request_id

        if self._log_params:
            logger.debug(
                "[%s] %s 开始 params=%s",
                request_id,
                method,
                _safe_params(ctx.params),
            )
        else:
            logger.debug("[%s] %s 开始", request_id, method)

        try:
            result = await next_handler(ctx)
        except MCPError as e:
            # 业务异常 — 记录错误日志但不吞没
            duration = ctx.duration_ms
            logger.warning(
                "[%s] %s 失败 duration=%.1fms error=%s message=%s",
                request_id,
                method,
                duration,
                e.error_code,
                e.message,
            )
            # 慢操作即使失败也要记录
            if duration > self._slow_threshold_ms:
                ctx.warn(
                    WARNING_SLOW_OPERATION,
                    f"操作耗时 {duration:.0f}ms（阈值 {self._slow_threshold_ms:.0f}ms）",
                    duration_ms=round(duration, 2),
                    threshold_ms=self._slow_threshold_ms,
                )
            raise
        except Exception as e:
            # 未预期异常 — 更高级别日志
            duration = ctx.duration_ms
            logger.error(
                "[%s] %s 内部错误 duration=%.1fms error=%s",
                request_id,
                method,
                duration,
                e,
                exc_info=True,
            )
            raise

        # 成功路径
        duration = ctx.duration_ms

        # 慢操作警告
        if duration > self._slow_threshold_ms:
            ctx.warn(
                WARNING_SLOW_OPERATION,
                f"操作耗时 {duration:.0f}ms（阈值 {self._slow_threshold_ms:.0f}ms）",
                duration_ms=round(duration, 2),
                threshold_ms=self._slow_threshold_ms,
            )

        logger.info(
            "[%s] %s 完成 duration=%.1fms warnings=%d",
            request_id,
            method,
            duration,
            len(ctx.warnings),
        )

        return result


def _safe_params(params: dict[str, Any], max_value_len: int = 100) -> dict[str, Any]:
    """
    安全化参数用于日志输出

    - 截断过长的值（content/patch 等大文本）
    - 不记录可能的敏感字段（env）
    """
    _SENSITIVE_KEYS = frozenset({"env"})
    safe = {}
    for key, value in params.items():
        if key in _SENSITIVE_KEYS:
            safe[key] = "<redacted>"
        elif isinstance(value, str) and len(value) > max_value_len:
            safe[key] = value[:max_value_len] + f"...(+{len(value) - max_value_len})"
        else:
            safe[key] = value
    return safe
