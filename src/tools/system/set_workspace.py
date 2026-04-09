"""动态切换工作区"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR
from ...handlers.base import RequestContext

tool = ToolDef(
    name="set_workspace",
    description="动态切换工作区根路径",
    lock="none",
    is_write=True,
    params=[
        param("root_path", STR, non_empty=True),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.set_workspace(ctx, **kwargs)
