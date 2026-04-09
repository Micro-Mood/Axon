"""同步执行命令"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, STR_OR_NONE, INT_OR_NONE, DICT_OR_NONE
from ...handlers.base import RequestContext

tool = ToolDef(
    name="run_command",
    description="同步执行命令并等待完成",
    lock="none",
    params=[
        param("command", STR, non_empty=True),
        param("cwd", STR_OR_NONE, required=False),
        param("timeout", INT_OR_NONE, required=False, min_value=1),
        param("env", DICT_OR_NONE, required=False),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.run(ctx, **kwargs)
