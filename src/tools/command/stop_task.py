"""优雅停止任务"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR
from ...handlers.base import RequestContext

tool = ToolDef(
    name="stop_task",
    description="发送信号优雅停止任务",
    lock="none",
    track="task_end",
    params=[
        param("task_id", STR, non_empty=True),
        param("signal", STR, required=False, default="interrupt"),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.stop(ctx, **kwargs)
