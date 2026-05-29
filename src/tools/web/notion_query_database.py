"""查询 Notion 数据库"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, STR_OR_NONE, INT
from ...handlers.base import RequestContext

tool = ToolDef(
    name="notion_query_database",
    description="按条件查询 Notion 数据库，返回精简条目列表（id/标题/URL/时间）",
    lock="none",
    params=[
        param("api_key", STR, non_empty=True),
        param("database_id", STR, non_empty=True),
        param("filter_json", STR_OR_NONE, required=False),
        param("sorts_json", STR_OR_NONE, required=False),
        param("page_size", INT, required=False, default=20, min_value=1, max_value=100),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.notion_query_database(ctx, **kwargs)
