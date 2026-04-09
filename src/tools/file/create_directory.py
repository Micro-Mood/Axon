"""创建目录"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, BOOL
from ...handlers.base import RequestContext

tool = ToolDef(
    name="create_directory",
    description="创建目录，支持递归创建",
    lock="dir_write",
    is_write=True,
    params=[
        param("path", STR, non_empty=True),
        param("recursive", BOOL, required=False, default=True),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.create_directory(ctx, **kwargs)
