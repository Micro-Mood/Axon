"""删除文件中指定行范围"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, INT
from ...handlers.base import RequestContext

tool = ToolDef(
    name="delete_range",
    description="删除文件中指定行范围",
    lock="write",
    is_write=True,
    params=[
        param("path", STR, non_empty=True),
        param("start_line", INT, min_value=1),
        param("end_line", INT, min_value=1),
        param("encoding", STR, required=False, default="utf-8"),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.delete_range(ctx, **kwargs)
