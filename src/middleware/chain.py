"""
Layer 5: Middleware — 中间件链调度器

职责:
- 定义 Middleware 协议（接口）
- 构建中间件链（洋葱模型）
- 将请求依次通过中间件，最终到达 handler

调用顺序:
    Security → Validation → RateLimit → Handler → Audit
    如果任何中间件抛异常，链中断，异常上浮

依赖:
- Layer 4: handlers/base (RequestContext)
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable

from ..handlers.base import RequestContext

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════
#  类型定义
# ═══════════════════════════════════════════════════════

# Handler 签名: (ctx) -> result
HandlerFunc = Callable[[RequestContext], Awaitable[dict[str, Any]]]

# Next 签名: 与 HandlerFunc 相同 — 调用下一个中间件或最终 handler
NextFunc = Callable[[RequestContext], Awaitable[dict[str, Any]]]


@runtime_checkable
class Middleware(Protocol):
    """
    中间件协议

    每个中间件实现 __call__(ctx, next) → result:
    - ctx: 请求上下文（可读写）
    - next: 调用链中的下一个中间件/handler
    - 返回: handler 的结果 dict

    中间件可以:
    1. 在 next() 之前做前置处理（校验参数、鉴权、限流）
    2. 在 next() 之后做后置处理（日志、耗时统计、结果包装）
    3. 捕获异常做错误处理
    4. 不调用 next() 来短路请求

    示例::

        class MyMiddleware:
            async def __call__(self, ctx, next):
                # 前置
                self.check_something(ctx)
                # 执行
                result = await next(ctx)
                # 后置
                result["extra"] = "injected"
                return result
    """

    async def __call__(
        self, ctx: RequestContext, next_handler: NextFunc
    ) -> dict[str, Any]: ...


# ═══════════════════════════════════════════════════════
#  中间件链
# ═══════════════════════════════════════════════════════

class MiddlewareChain:
    """
    洋葱模型中间件链

    将多个中间件组合为一个可调用对象:

        chain = MiddlewareChain()
        chain.use(security_middleware)
        chain.use(validation_middleware)
        chain.use(rate_limit_middleware)
        chain.use(audit_middleware)

        result = await chain.execute(ctx, handler)

    执行顺序（洋葱模型）:
        → security 前置
          → validation 前置
            → rate_limit 前置
              → handler 执行
            ← rate_limit 后置
          ← validation 后置
        ← security 后置

    注意: AuditMiddleware 应放在最外层（第一个 use），
    这样它能测到完整链路耗时并捕获所有异常。
    但按架构设计，audit 放最后，因为它只是记日志。
    """

    def __init__(self) -> None:
        self._middlewares: list[Middleware] = []

    def use(self, middleware: Middleware) -> MiddlewareChain:
        """
        注册中间件

        按注册顺序执行:
        - 第一个 use 的中间件最先拿到请求
        - 最后一个 use 的中间件最靠近 handler

        Args:
            middleware: 实现 Middleware 协议的对象

        Returns:
            self，支持链式调用
        """
        self._middlewares.append(middleware)
        return self

    def clear(self) -> None:
        """清空所有中间件"""
        self._middlewares.clear()

    @property
    def middlewares(self) -> list[Middleware]:
        """当前注册的中间件列表（只读副本）"""
        return list(self._middlewares)

    async def execute(
        self, ctx: RequestContext, handler: HandlerFunc
    ) -> dict[str, Any]:
        """
        执行中间件链

        将中间件按注册顺序包裹 handler，构建调用链后执行。

        Args:
            ctx: 请求上下文
            handler: 最终的业务 handler 函数

        Returns:
            handler 的返回结果（可能被中间件修改）

        Raises:
            MCPError: 中间件或 handler 抛出的业务异常
            Exception: 未预期的内部错误
        """
        # 从最内层（最后注册的中间件）向外构建调用链
        # 最内层直接包裹 handler
        current: NextFunc = handler

        for middleware in reversed(self._middlewares):
            current = _wrap_middleware(middleware, current)

        return await current(ctx)

    def __len__(self) -> int:
        return len(self._middlewares)

    def __repr__(self) -> str:
        names = [type(m).__name__ for m in self._middlewares]
        return f"MiddlewareChain([{' → '.join(names)}])"


def _wrap_middleware(middleware: Middleware, next_func: NextFunc) -> NextFunc:
    """
    将一个中间件和它的 next 包装为一个新的 NextFunc

    这是构建洋葱模型的核心: 每层中间件接收 (ctx, next)，
    next 是下一层的入口。
    """

    async def wrapped(ctx: RequestContext) -> dict[str, Any]:
        return await middleware(ctx, next_func)

    # 保留中间件类名，方便调试
    wrapped.__qualname__ = f"{type(middleware).__name__}._wrapped"
    return wrapped
