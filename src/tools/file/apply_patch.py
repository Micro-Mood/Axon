"""应用 unified diff 补丁"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, BOOL
from ...handlers.base import RequestContext

tool = ToolDef(
    name="apply_patch",
    description="应用 unified diff 格式的补丁",
    lock="write",
    is_write=True,
    params=[
        param("path", STR, non_empty=True),
        param("patch", STR, non_empty=True),
        param("dry_run", BOOL, required=False, default=False),
        param("encoding", STR, required=False, default="utf-8"),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.apply_patch(ctx, **kwargs)
