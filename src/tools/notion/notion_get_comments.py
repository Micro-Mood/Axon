"""获取 Notion 页面/block 的评论列表"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, INT
from ...handlers.base import RequestContext

tool = ToolDef(
    name="notion_get_comments",
    description="获取 Notion 页面或 block 上的评论列表（需要集成具备评论读取权限）",
    lock="none",
    params=[
        param("api_key", STR, non_empty=True),
        param("block_id", STR, non_empty=True),
        param("page_size", INT, required=False, default=20, min_value=1, max_value=100),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.notion_get_comments(ctx, **kwargs)
