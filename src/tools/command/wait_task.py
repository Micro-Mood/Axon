"""等待任务完成"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, INT_OR_NONE
from ...handlers.base import RequestContext

tool = ToolDef(
    name="wait_task",
    description="等待异步任务完成",
    lock="none",
    params=[
        param("task_id", STR, non_empty=True),
        param("timeout", INT_OR_NONE, required=False, min_value=1),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.wait(ctx, **kwargs)
