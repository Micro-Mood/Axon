"""
Layer 6: Protocol — 方法路由器

职责:
- 将 JSON-RPC method 名 → handler 可调用对象
- handler 方法注册（自动从 Handler 实例收集公开方法）
- 参数适配: JSON params dict → handler 关键字参数
- 方法列表查询（供 SystemHandler.get_methods 使用）

设计:
- 纯映射，无 I/O，无状态（注册完成后只读）
- handler 签名: async def xxx(self, ctx: RequestContext, **kwargs) → dict
- router 包装后的签名: async def (ctx: RequestContext) → dict
  其中 kwargs 从 ctx.params 提取，匹配 handler 的参数名

依赖:
- Layer 4: handlers/base (RequestContext)
- Layer 4: handlers (FileHandler, SearchHandler, CommandHandler, SystemHandler)
"""

from __future__ import annotations

import inspect
import logging
import typing
from pathlib import Path
from typing import Any, Awaitable, Callable

from ..handlers.base import RequestContext

logger = logging.getLogger(__name__)

# Router 包装后的统一签名
HandlerFunc = Callable[[RequestContext], Awaitable[dict[str, Any]]]


class MethodRouter:
    """
    方法路由器

    负责将 JSON-RPC method 名映射到 handler 方法。

    注册方式::

        router = MethodRouter()
        router.register("read_file", file_handler.read_file)
        router.register("ping", system_handler.ping)

    或批量::

        router.register_handler(file_handler, {
            "read_file": "read_file",
            "write_file": "write_file",
        })

    调用::

        handler_fn = router.resolve("read_file")
        result = await handler_fn(ctx)  # ctx.params 自动展开为 kwargs
    """

    def __init__(self) -> None:
        self._routes: dict[str, HandlerFunc] = {}
        # 保存原始方法引用，供参数检查/文档生成
        self._raw_methods: dict[str, Callable] = {}

    def register(self, method_name: str, handler_method: Callable) -> None:
        """
        注册单个方法

        Args:
            method_name: JSON-RPC method 名 (e.g. "read_file")
            handler_method: handler 的绑定方法 (e.g. file_handler.read_file)
        """
        if method_name in self._routes:
            logger.warning("方法 %s 被重复注册，覆盖", method_name)

        self._raw_methods[method_name] = handler_method
        self._routes[method_name] = self._wrap(handler_method)

    def register_handler(
        self,
        handler: Any,
        method_map: dict[str, str],
    ) -> None:
        """
        批量注册某个 handler 实例的方法

        Args:
            handler: handler 实例 (e.g. FileHandler)
            method_map: {json_rpc_method: handler_attr_name}
                e.g. {"read_file": "read_file", "run_command": "run"}
        """
        for rpc_name, attr_name in method_map.items():
            method = getattr(handler, attr_name, None)
            if method is None:
                raise ValueError(
                    f"Handler {type(handler).__name__} 没有方法 {attr_name}"
                )
            if not callable(method):
                raise ValueError(
                    f"{type(handler).__name__}.{attr_name} 不是可调用对象"
                )
            self.register(rpc_name, method)

    def resolve(self, method_name: str) -> HandlerFunc | None:
        """
        查找方法

        Args:
            method_name: JSON-RPC method 名

        Returns:
            包装后的 handler 函数，或 None 表示未注册
        """
        return self._routes.get(method_name)

    @property
    def methods(self) -> list[str]:
        """已注册的全部方法名（排序）"""
        return sorted(self._routes.keys())

    @property
    def method_count(self) -> int:
        """已注册方法数量"""
        return len(self._routes)

    def get_method_signature(self, method_name: str) -> dict[str, Any] | None:
        """
        获取某个方法的参数签名

        用于调试/文档生成，不在热路径。

        Returns:
            {"params": {name: {type, default, required}}} 或 None
        """
        raw = self._raw_methods.get(method_name)
        if raw is None:
            return None

        sig = inspect.signature(raw)
        params = {}
        for name, param in sig.parameters.items():
            # 跳过 self 和 ctx
            if name in ("self", "ctx"):
                continue
            info: dict[str, Any] = {
                "required": param.default is inspect.Parameter.empty,
            }
            if param.annotation is not inspect.Parameter.empty:
                info["type"] = _format_annotation(param.annotation)
            if param.default is not inspect.Parameter.empty:
                info["default"] = param.default
            params[name] = info

        return {"params": params}

    @staticmethod
    def _wrap(handler_method: Callable) -> HandlerFunc:
        """
        包装 handler 方法为统一的 HandlerFunc 签名

        从 ctx.params 中提取 handler 需要的参数，
        跳过 self 和 ctx 参数。
        不认识的参数忽略（靠 ValidationMiddleware 已经过滤了）。
        """
        sig = inspect.signature(handler_method)
        # 提取 handler 需要的参数名（排除 self 和 ctx）
        param_names = [
            name
            for name in sig.parameters
            if name not in ("self", "ctx")
        ]

        # 预构建参数名到 Path 的映射，用于 str→Path 自动转换
        # 使用 get_type_hints() 解析字符串注解（from __future__ import annotations）
        try:
            resolved = typing.get_type_hints(handler_method)
        except Exception:
            resolved = {}
        _path_params: set[str] = set()
        for name in param_names:
            ann = resolved.get(name)
            if ann is Path:
                _path_params.add(name)

        async def wrapped(ctx: RequestContext) -> dict[str, Any]:
            kwargs = {}
            for name in param_names:
                if name in ctx.params:
                    value = ctx.params[name]
                    # 类型转换: str → Path
                    if name in _path_params and isinstance(value, str):
                        value = Path(value)
                    kwargs[name] = value
                else:
                    # 检查是否有默认值
                    param = sig.parameters[name]
                    if param.default is inspect.Parameter.empty:
                        # 缺少必选参数 — 这里不处理，
                        # ValidationMiddleware 已在前面拦截
                        pass
            return await handler_method(ctx, **kwargs)

        return wrapped

    def __contains__(self, method_name: str) -> bool:
        return method_name in self._routes

    def __len__(self) -> int:
        return len(self._routes)

    def __repr__(self) -> str:
        return f"MethodRouter({self.method_count} methods)"


def _format_annotation(annotation: Any) -> str:
    """格式化类型注解为字符串"""
    if hasattr(annotation, "__name__"):
        return annotation.__name__
    return str(annotation)
