"""删除目录"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, BOOL
from ...handlers.base import RequestContext

tool = ToolDef(
    name="delete_directory",
    description="删除目录，支持递归和强制删除",
    lock="dir_write",
    is_write=True,
    params=[
        param("path", STR, non_empty=True),
        param("recursive", BOOL, required=False, default=False),
        param("force", BOOL, required=False, default=False),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.delete_directory(ctx, **kwargs)
