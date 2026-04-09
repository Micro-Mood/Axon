"""检查文件/目录是否存在"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR
from ...handlers.base import RequestContext

tool = ToolDef(
    name="exists",
    description="检查文件或目录是否存在",
    lock="read",
    params=[
        param("path", STR, non_empty=True),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.exists(ctx, **kwargs)
