"""读取 Notion 页面内容"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, BOOL
from ...handlers.base import RequestContext

tool = ToolDef(
    name="notion_get_page",
    description="获取 Notion 页面的元数据和正文内容（最多两层 block）",
    lock="none",
    params=[
        param("api_key", STR, non_empty=True),
        param("page_id", STR, non_empty=True),
        param("include_content", BOOL, required=False, default=True),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.notion_get_page(ctx, **kwargs)
