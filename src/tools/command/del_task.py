"""删除已完成的异步任务，释放内存"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR
from ...handlers.base import RequestContext

tool = ToolDef(
    name="del_task",
    description="删除已完成的异步任务及其输出缓冲区，释放内存",
    lock="none",
    params=[
        param("task_id", STR, non_empty=True),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.delete_task(ctx, **kwargs)
