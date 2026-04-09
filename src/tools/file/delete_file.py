"""删除文件"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR
from ...handlers.base import RequestContext

tool = ToolDef(
    name="delete_file",
    description="删除指定文件",
    lock="write",
    is_write=True,
    params=[
        param("path", STR, non_empty=True),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.delete_file(ctx, **kwargs)
