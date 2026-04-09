"""读取文件内容"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, STR_OR_NONE, INT_OR_NONE, TUPLE_INT_INT_OR_NONE
from ...handlers.base import RequestContext

tool = ToolDef(
    name="read_file",
    description="读取文件内容，支持编码检测和行范围截取",
    lock="read",
    params=[
        param("path", STR, non_empty=True),
        param("encoding", STR_OR_NONE, required=False),
        param("line_range", TUPLE_INT_INT_OR_NONE, required=False),
        param("max_size", INT_OR_NONE, required=False, min_value=1),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.read_file(ctx, **kwargs)
