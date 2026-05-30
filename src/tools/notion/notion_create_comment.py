"""在 Notion 页面/block 上添加评论"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR
from ...handlers.base import RequestContext

tool = ToolDef(
    name="notion_create_comment",
    description="在 Notion 页面上添加新评论（需要集成具备评论写入权限）",
    lock="none",
    is_write=True,
    params=[
        param("api_key", STR, non_empty=True),
        param("block_id", STR, non_empty=True),
        param("content", STR, non_empty=True),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.notion_create_comment(ctx, **kwargs)
