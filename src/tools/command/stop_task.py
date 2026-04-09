"""停止异步任务"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, BOOL
from ...handlers.base import RequestContext

tool = ToolDef(
    name="stop_task",
    description="停止异步任务。默认优雅停止（发送中断信号），force=true 则强制终止",
    lock="none",
    track="task_end",
    params=[
        param("task_id", STR, non_empty=True),
        param("force", BOOL, required=False, default=False),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.stop(ctx, **kwargs)
