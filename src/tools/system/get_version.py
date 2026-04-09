"""版本信息"""
from __future__ import annotations

from typing import Any

from .. import ToolDef
from ...handlers.base import RequestContext

tool = ToolDef(
    name="get_version",
    description="获取服务版本信息",
    lock="none",
    params=[],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.get_version(ctx)
