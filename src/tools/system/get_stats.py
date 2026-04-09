"""获取缓存统计"""
from __future__ import annotations

from typing import Any

from .. import ToolDef
from ...handlers.base import RequestContext

tool = ToolDef(
    name="get_stats",
    description="获取服务缓存和运行时统计",
    lock="none",
    params=[],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.get_stats(ctx)
