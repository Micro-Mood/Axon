"""在指定行之前插入文本"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, INT
from ...handlers.base import RequestContext

tool = ToolDef(
    name="insert_text",
    description="在指定行之前插入文本",
    lock="write",
    is_write=True,
    params=[
        param("path", STR, non_empty=True),
        param("line", INT, min_value=1),
        param("text", STR),
        param("encoding", STR, required=False, default="utf-8"),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.insert_text(ctx, **kwargs)
