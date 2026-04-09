"""
Layer 6: Protocol — MCP Server 主体

职责:
- 初始化全部下层组件（config, security, cache, handlers, middleware）
- 将 handler 方法注册到 MethodRouter
- 调度请求: JSON-RPC 解析 → 路由 → 中间件链执行 → 响应格式化
- 生命周期管理（startup / shutdown / cleanup）

这是整个 Axon 的中枢，将 6 层架构串联为一条完整的请求处理链。

依赖:
- Layer 1: core (config, security, cache, errors, resource, filelock)
- Layer 4: handlers (file, search, command, system)
- Layer 5: middleware (build_default_chain)
- Layer 6: protocol (router, jsonrpc)
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from ..core.cache import CacheManager
from ..core.config import ConfigHolder, MCPConfig, load_config
from ..core.errors import MCPError
from ..core.filelock import AsyncFileLockManager
from ..core.resource import ResourceTracker
from ..core.security import SecurityChecker
from ..handlers.base import RequestContext
from ..handlers.command import CommandHandler
from ..handlers.file import FileHandler
from ..handlers.search import SearchHandler
from ..handlers.system import SystemHandler
from ..middleware import build_default_chain
from ..middleware.chain import MiddlewareChain
from ..stream import StreamManager
from ..tools import discover_all
from .jsonrpc import (
    JsonRpcError,
    JsonRpcRequest,
    METHOD_NOT_FOUND,
    batch_response,
    error_response,
    map_internal_error,
    map_mcp_error,
    parse_request,
    success_response,
)
from .router import MethodRouter

logger = logging.getLogger(__name__)


class MCPServer:
    """
    Axon MCP Server

    完整的请求处理链::

        客户端 JSON
          → parse_request (jsonrpc.py)
          → MethodRouter.resolve (router.py)
          → MiddlewareChain.execute (middleware/chain.py)
            → Security → Validation → RateLimit → Concurrency
              → Handler 方法
            → Audit
          → success_response / error_response (jsonrpc.py)
        → 返回 JSON

    用法::

        config = load_config("config.json")
        server = MCPServer(config)
        await server.startup()

        response_json = await server.handle_request(request_json)

        await server.shutdown()
    """

    def __init__(self, config: MCPConfig | None = None) -> None:
        self._config = config or MCPConfig()
        self._started = False

        # ── Layer 1: Core ──
        self._config_holder = ConfigHolder(self._config)
        self._security = SecurityChecker(self._config.security)
        self._cache = CacheManager()
        self._resource_tracker = ResourceTracker(self._config.performance)
        self._file_lock_manager = AsyncFileLockManager()

        # ── Layer 3: Stream ──
        self._stream_manager = StreamManager(
            self._config.performance.max_output_buffer_mb * 1024 * 1024
        )

        # ── Layer 4: Handlers ──
        self._file_handler = FileHandler(self._config, self._cache)
        self._search_handler = SearchHandler(self._config, self._cache)
        self._command_handler = CommandHandler(
            self._config, self._cache,
            self._stream_manager,
            self._security,
        )
        self._system_handler = SystemHandler(
            self._config, self._cache,
            self._config_holder,
        )

        # ── Layer 6: Router ──
        self._router = MethodRouter()
        self._tools = discover_all()
        self._register_methods()

        # ── Layer 5: Middleware Chain ──
        self._chain = build_default_chain(
            self._config,
            self._security,
            file_lock_manager=self._file_lock_manager,
            resource_tracker=self._resource_tracker,
            tools=self._tools,
        )

        # 注入方法列表到 SystemHandler
        self._system_handler.set_registered_methods(self._router.methods)

    # ═══════════════════════════════════════════════════
    #  方法注册
    # ═══════════════════════════════════════════════════

    def _register_methods(self) -> None:
        """将所有 tool 注册到路由器（自动扫描 tools/ 目录）"""

        handler_map = {
            "file": self._file_handler,
            "search": self._search_handler,
            "command": self._command_handler,
            "system": self._system_handler,
        }

        for name, tool_def in self._tools.items():
            handler = handler_map.get(tool_def.group)
            if handler is None:
                logger.warning("tool %s 的 group '%s' 无对应 handler，跳过", name, tool_def.group)
                continue
            self._router.register_tool(tool_def, handler)

        logger.info("已注册 %d 个方法（来自 tools/ 自动扫描）", self._router.method_count)

    # ═══════════════════════════════════════════════════
    #  请求处理
    # ═══════════════════════════════════════════════════

    async def handle_request(self, raw: str | bytes) -> str:
        """
        处理一条 JSON-RPC 请求

        完整链路:
        1. 解析 JSON-RPC
        2. 路由到 handler
        3. 通过中间件链执行
        4. 格式化响应

        Args:
            raw: 原始 JSON 字符串或字节

        Returns:
            JSON-RPC 响应字符串（永远不抛异常）
        """
        parsed = parse_request(raw)

        # 解析失败
        if isinstance(parsed, JsonRpcError):
            return error_response(None, parsed)

        # 批量请求
        if isinstance(parsed, list):
            return await self._handle_batch(parsed)

        # 单条请求
        return await self._handle_single(parsed)

    async def _handle_single(self, req: JsonRpcRequest) -> str:
        """处理单条 JSON-RPC 请求"""
        # 通知（无 id）— 执行但不返回
        # JSON-RPC 规范: 通知不需要响应
        if req.is_notification:
            await self._execute(req)
            return ""

        # 查找方法
        handler_fn = self._router.resolve(req.method)
        if handler_fn is None:
            return error_response(
                req.id,
                JsonRpcError(
                    code=METHOD_NOT_FOUND,
                    message=f"未知方法: {req.method}",
                    data={"method": req.method, "available": self._router.methods},
                ),
            )

        # 构造上下文
        ctx = RequestContext(
            method=req.method,
            params=req.params,
        )
        if req.id is not None:
            ctx.request_id = str(req.id)

        # 通过中间件链执行
        try:
            result = await self._chain.execute(ctx, handler_fn)
        except MCPError as e:
            return error_response(req.id, map_mcp_error(e))
        except Exception as e:
            logger.exception("请求处理异常: method=%s id=%s", req.method, req.id)
            return error_response(req.id, map_internal_error(e))

        # 收集警告
        warnings = [w.to_dict() for w in ctx.warnings] if ctx.warnings else None

        return success_response(req.id, result, warnings)

    async def _handle_batch(self, requests: list[JsonRpcRequest]) -> str:
        """
        处理批量请求

        并发执行所有子请求（受中间件限流/并发控制）。
        通知请求不产生响应。
        """
        tasks = [self._handle_single(req) for req in requests]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        responses = []
        for req, result in zip(requests, results):
            if req.is_notification:
                continue  # 通知无响应
            if isinstance(result, Exception):
                logger.exception("批量请求子项异常: method=%s", req.method)
                responses.append(
                    error_response(req.id, map_internal_error(result))
                )
            else:
                responses.append(result)

        if not responses:
            return ""  # 全部是通知

        return batch_response(responses)

    async def _execute(self, req: JsonRpcRequest) -> dict[str, Any] | None:
        """执行请求但不处理响应格式（用于通知）"""
        handler_fn = self._router.resolve(req.method)
        if handler_fn is None:
            return None

        ctx = RequestContext(method=req.method, params=req.params)
        try:
            return await self._chain.execute(ctx, handler_fn)
        except Exception:
            logger.exception("通知处理异常: method=%s", req.method)
            return None

    # ═══════════════════════════════════════════════════
    #  生命周期
    # ═══════════════════════════════════════════════════

    async def startup(self) -> None:
        """
        服务启动

        初始化需要异步操作的组件。
        """
        if self._started:
            return

        logger.info(
            "Axon MCP Server 启动: %s:%d (%s)",
            self._config.server.host,
            self._config.server.port,
            self._config.server.transport,
        )
        logger.info("工作区: %s", self._config.workspace.root)
        logger.info("已注册方法: %d", self._router.method_count)

        self._started = True

    async def shutdown(self) -> None:
        """
        服务关闭

        清理顺序（与启动相反）:
        1. 停止接受新请求
        2. 等待/停止活跃任务
        3. 清理流管理器
        4. 清理缓存
        5. 清理文件锁
        """
        if not self._started:
            return

        logger.info("Axon MCP Server 关闭中...")

        # 清理活跃任务
        try:
            cleaned = await self._command_handler.cleanup_completed()
            if cleaned:
                logger.info("清理完成的任务: %d", cleaned)
        except Exception:
            logger.exception("任务清理异常")

        # 清理文件锁
        try:
            evicted = await self._file_lock_manager.cleanup()
            if evicted:
                logger.info("清理文件锁: %d", evicted)
        except Exception:
            logger.exception("文件锁清理异常")

        # 重置资源追踪
        await self._resource_tracker.reset()

        # 清理缓存
        self._cache.clear()

        self._started = False
        logger.info("Axon MCP Server 已关闭")

    @property
    def config(self) -> MCPConfig:
        return self._config

    @property
    def router(self) -> MethodRouter:
        return self._router

    @property
    def is_running(self) -> bool:
        return self._started
