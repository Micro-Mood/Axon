"""更新 Notion 页面的标题或属性字段"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, STR_OR_NONE
from ...handlers.base import RequestContext

tool = ToolDef(
    name="notion_update_page",
    description="更新 Notion 页面的标题或属性字段（title 和 properties_json 至少提供一个）",
    lock="none",
    is_write=True,
    params=[
        param("api_key", STR, non_empty=True),
        param("page_id", STR, non_empty=True),
        param("title", STR_OR_NONE, required=False),
        param("properties_json", STR_OR_NONE, required=False),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.notion_update_page(ctx, **kwargs)
