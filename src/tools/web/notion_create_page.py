"""在 Notion 中创建新页面"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, STR_OR_NONE
from ...handlers.base import RequestContext

tool = ToolDef(
    name="notion_create_page",
    description="在 Notion 中创建新页面或数据库条目",
    lock="none",
    is_write=True,
    params=[
        param("api_key", STR, non_empty=True),
        param("parent_id", STR, non_empty=True),
        param("parent_type", STR, non_empty=True),   # "page" | "database"
        param("title", STR, non_empty=True),
        param("content", STR_OR_NONE, required=False),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.notion_create_page(ctx, **kwargs)
