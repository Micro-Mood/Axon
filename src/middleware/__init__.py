"""
Layer 5: Middleware（中间件层）

提供:
- MiddlewareChain: 洋葱模型中间件链调度器
- SecurityMiddleware: 路径/命令/环境变量自动安全校验
- ValidationMiddleware: 参数类型/范围/必选校验
- AuditMiddleware: 审计日志 + 慢操作警告
- RateLimitMiddleware: 滑动窗口限流
- build_default_chain(): 按架构设计构建默认中间件链

调用顺序:
    Security → Validation → RateLimit → Handler → Audit

依赖:
- Layer 1: core (MCPConfig, SecurityChecker, errors)
- Layer 4: handlers/base (RequestContext)
"""

from __future__ import annotations

from ..core.config import MCPConfig
from ..core.security import SecurityChecker

from .chain import HandlerFunc, Middleware, MiddlewareChain, NextFunc
from .security import SecurityMiddleware
from .validation import ValidationMiddleware, get_method_schema, get_registered_methods
from .audit import AuditMiddleware
from .rate_limit import RateLimitMiddleware


def build_default_chain(
    config: MCPConfig,
    security: SecurityChecker,
    *,
    rate_limit_enabled: bool = True,
    strict_validation: bool = False,
    slow_threshold_ms: float = 5000.0,
    log_params: bool = False,
    global_rpm: int = 600,
    read_rpm: int = 300,
    write_rpm: int = 60,
) -> MiddlewareChain:
    """
    按架构设计构建默认中间件链

    顺序: Security → Validation → RateLimit → [Handler] → Audit

    注意: Audit 作为最后注册的中间件，在洋葱模型中最靠近 handler，
    因此它测量的是去掉前置校验后的纯 handler 执行时间。

    Args:
        config: 全局配置
        security: 安全校验器实例
        rate_limit_enabled: 是否启用限流
        strict_validation: 严格参数校验模式（拒绝未知参数）
        slow_threshold_ms: 慢操作警告阈值
        log_params: 审计日志是否记录请求参数
        global_rpm: 全局每分钟请求上限
        read_rpm: 读操作每分钟上限
        write_rpm: 写操作每分钟上限

    Returns:
        配置好的 MiddlewareChain 实例
    """
    chain = MiddlewareChain()

    # 1. 安全校验 — 最外层，第一个拦截请求
    chain.use(SecurityMiddleware(config, security))

    # 2. 参数校验 — 安全通过后，校验参数格式
    chain.use(ValidationMiddleware(strict=strict_validation))

    # 3. 限流 — 校验通过后，检查频率
    chain.use(RateLimitMiddleware(
        global_rpm=global_rpm,
        read_rpm=read_rpm,
        write_rpm=write_rpm,
        enabled=rate_limit_enabled,
    ))

    # 4. 审计 — 最靠近 handler，记录执行情况
    chain.use(AuditMiddleware(
        slow_threshold_ms=slow_threshold_ms,
        log_params=log_params,
    ))

    return chain


__all__ = [
    # Chain
    "MiddlewareChain",
    "Middleware",
    "HandlerFunc",
    "NextFunc",
    # Middlewares
    "SecurityMiddleware",
    "ValidationMiddleware",
    "AuditMiddleware",
    "RateLimitMiddleware",
    # Builder
    "build_default_chain",
    # Utilities
    "get_method_schema",
    "get_registered_methods",
]
