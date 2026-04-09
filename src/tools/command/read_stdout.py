"""读取标准输出"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, INT
from ...handlers.base import RequestContext

tool = ToolDef(
    name="read_stdout",
    description="读取任务标准输出（消费式）",
    lock="none",
    params=[
        param("task_id", STR, non_empty=True),
        param("max_chars", INT, required=False, default=8192, min_value=1),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.read_stdout(ctx, **kwargs)
