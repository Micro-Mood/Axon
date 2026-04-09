"""获取文件/目录元信息"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, BOOL
from ...handlers.base import RequestContext

tool = ToolDef(
    name="stat_path",
    description="获取文件或目录的详细元信息",
    lock="read",
    params=[
        param("path", STR, non_empty=True),
        param("follow_symlinks", BOOL, required=False, default=True),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.stat_path(ctx, **kwargs)
