"""列出目录内容"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, STR_OR_NONE, BOOL, INT_OR_NONE
from ...handlers.base import RequestContext

tool = ToolDef(
    name="list_directory",
    description="列出目录内容，支持 glob 过滤和递归",
    lock="none",
    params=[
        param("path", STR, non_empty=True),
        param("pattern", STR_OR_NONE, required=False),
        param("recursive", BOOL, required=False, default=False),
        param("include_hidden", BOOL, required=False, default=False),
        param("max_results", INT_OR_NONE, required=False, min_value=1),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.list_directory(ctx, **kwargs)
