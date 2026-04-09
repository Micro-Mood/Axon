"""查询任务状态"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR
from ...handlers.base import RequestContext

tool = ToolDef(
    name="task_status",
    description="查询异步任务的状态",
    lock="none",
    params=[
        param("task_id", STR, non_empty=True),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.status(ctx, **kwargs)
