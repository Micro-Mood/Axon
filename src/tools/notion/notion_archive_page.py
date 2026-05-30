"""将 Notion 页面归档（移入回收站，可在 Notion 界面恢复）"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR
from ...handlers.base import RequestContext

tool = ToolDef(
    name="notion_archive_page",
    description="将 Notion 页面归档（移入回收站），可在 Notion 界面恢复",
    lock="none",
    is_write=True,
    params=[
        param("api_key", STR, non_empty=True),
        param("page_id", STR, non_empty=True),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.notion_archive_page(ctx, **kwargs)
