"""健康检查"""
from __future__ import annotations

from typing import Any

from .. import ToolDef
from ...handlers.base import RequestContext

tool = ToolDef(
    name="ping",
    description="服务健康检查",
    lock="none",
    params=[],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.ping(ctx)
