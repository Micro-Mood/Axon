"""移动/重命名目录"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR
from ...handlers.base import RequestContext

tool = ToolDef(
    name="move_directory",
    description="移动或重命名目录",
    lock="dir_write",
    is_write=True,
    params=[
        param("source", STR, non_empty=True),
        param("dest", STR, non_empty=True),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.move_directory(ctx, **kwargs)
