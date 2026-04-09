"""移动/重命名文件"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, BOOL
from ...handlers.base import RequestContext

tool = ToolDef(
    name="move_file",
    description="移动或重命名文件",
    lock="write_dual",
    is_write=True,
    params=[
        param("source", STR, non_empty=True),
        param("dest", STR, non_empty=True),
        param("overwrite", BOOL, required=False, default=False),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.move_file(ctx, **kwargs)
