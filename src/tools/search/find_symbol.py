"""搜索代码符号（函数、类、变量定义）"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, STR_OR_NONE, BOOL, INT_OR_NONE
from ...handlers.base import RequestContext

tool = ToolDef(
    name="find_symbol",
    description="搜索代码符号（函数、类、变量定义）",
    lock="none",
    params=[
        param("symbol", STR, non_empty=True),
        param("root", STR_OR_NONE, required=False),
        param("symbol_type", STR_OR_NONE, required=False),
        param("file_pattern", STR, required=False, default="*"),
        param("include_hidden", BOOL, required=False, default=False),
        param("max_results", INT_OR_NONE, required=False, min_value=1),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.find_symbol(ctx, **kwargs)
