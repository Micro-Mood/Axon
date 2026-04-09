"""创建并启动异步任务"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, STR_OR_NONE, INT_OR_NONE, DICT_OR_NONE
from ...handlers.base import RequestContext

tool = ToolDef(
    name="create_task",
    description="创建并启动异步命令任务",
    lock="none",
    track="task_create",
    params=[
        param("command", STR, non_empty=True),
        param("cwd", STR_OR_NONE, required=False),
        param("timeout", INT_OR_NONE, required=False, min_value=1),
        param("env", DICT_OR_NONE, required=False),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.spawn(ctx, **kwargs)
