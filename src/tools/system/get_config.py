"""获取当前配置"""
from __future__ import annotations

from typing import Any

from .. import ToolDef
from ...handlers.base import RequestContext

tool = ToolDef(
    name="get_config",
    description="获取当前服务配置（脱敏）",
    lock="none",
    params=[],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.get_config(ctx)
