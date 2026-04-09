"""按文件名/glob 模式搜索"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, STR_OR_NONE, BOOL, INT_OR_NONE, LIST_OR_NONE
from ...handlers.base import RequestContext

tool = ToolDef(
    name="find_files",
    description="按文件名或 glob 模式搜索文件",
    lock="none",
    params=[
        param("pattern", STR, non_empty=True),
        param("root", STR_OR_NONE, required=False),
        param("recursive", BOOL, required=False, default=True),
        param("file_types", LIST_OR_NONE, required=False),
        param("include_hidden", BOOL, required=False, default=False),
        param("max_results", INT_OR_NONE, required=False, min_value=1),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.find_files(ctx, **kwargs)
