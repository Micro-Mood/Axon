"""搜索 Notion 页面和数据库"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, STR_OR_NONE, INT
from ...handlers.base import RequestContext

tool = ToolDef(
    name="notion_search",
    description="搜索 Notion 工作区中的页面和数据库",
    lock="none",
    params=[
        param("api_key", STR, non_empty=True),
        param("query", STR, non_empty=True),
        param("filter_type", STR_OR_NONE, required=False),  # "page" | "database"
        param("page_size", INT, required=False, default=10, min_value=1, max_value=100),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.notion_search(ctx, **kwargs)
