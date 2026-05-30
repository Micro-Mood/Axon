"""列出 Notion 工作区成员"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, INT
from ...handlers.base import RequestContext

tool = ToolDef(
    name="notion_list_users",
    description="列出 Notion 工作区的所有成员（需要集成具备用户读取权限）",
    lock="none",
    params=[
        param("api_key", STR, non_empty=True),
        param("page_size", INT, required=False, default=20, min_value=1, max_value=100),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.notion_list_users(ctx, **kwargs)
