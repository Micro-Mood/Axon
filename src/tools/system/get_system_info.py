"""获取系统环境信息"""
from __future__ import annotations

from typing import Any

from .. import ToolDef
from ...handlers.base import RequestContext

tool = ToolDef(
    name="get_system_info",
    description="获取系统环境信息：操作系统、架构、Python版本、Shell类型、工作区路径",
    lock="none",
    params=[],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.get_system_info(ctx)
