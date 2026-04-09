"""替换文件中指定行范围的文本"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, INT
from ...handlers.base import RequestContext

tool = ToolDef(
    name="replace_range",
    description="替换文件中指定行范围的文本",
    lock="write",
    is_write=True,
    params=[
        param("path", STR, non_empty=True),
        param("start_line", INT, min_value=1),
        param("end_line", INT, min_value=1),
        param("new_text", STR),
        param("encoding", STR, required=False, default="utf-8"),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.replace_range(ctx, **kwargs)
