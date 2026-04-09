"""强制终止任务"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR
from ...handlers.base import RequestContext

tool = ToolDef(
    name="kill_task",
    description="强制终止任务（SIGKILL）",
    lock="none",
    track="task_end",
    params=[
        param("task_id", STR, non_empty=True),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.kill(ctx, **kwargs)
