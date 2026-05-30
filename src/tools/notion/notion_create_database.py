"""在 Notion 页面下创建新的内联数据库"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, STR_OR_NONE
from ...handlers.base import RequestContext

tool = ToolDef(
    name="notion_create_database",
    description="在 Notion 页面下创建新的内联数据库",
    lock="none",
    is_write=True,
    params=[
        param("api_key", STR, non_empty=True),
        param("parent_id", STR, non_empty=True),
        param("title", STR, non_empty=True),
        param("properties_json", STR_OR_NONE, required=False),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.notion_create_database(ctx, **kwargs)
