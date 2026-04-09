"""写入标准输入"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, BOOL
from ...handlers.base import RequestContext

tool = ToolDef(
    name="write_stdin",
    description="向任务标准输入写入数据",
    lock="none",
    params=[
        param("task_id", STR, non_empty=True),
        param("data", STR),
        param("eof", BOOL, required=False, default=False),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.write_stdin(ctx, **kwargs)
