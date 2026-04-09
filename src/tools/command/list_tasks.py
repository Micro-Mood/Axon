"""列出所有任务"""
from __future__ import annotations

from typing import Any

from .. import ToolDef
from ...handlers.base import RequestContext

tool = ToolDef(
    name="list_tasks",
    description="列出所有异步任务",
    lock="none",
    params=[],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.list_tasks(ctx)
