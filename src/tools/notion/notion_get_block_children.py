"""分页读取 Notion block/页面的子节点列表"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, STR_OR_NONE, INT
from ...handlers.base import RequestContext

tool = ToolDef(
    name="notion_get_block_children",
    description=(
        "分页读取 Notion block 或页面的子节点列表。"
        "当 notion_get_page 返回 has_more=true 时，用 next_cursor 作为 start_cursor 续读"
    ),
    lock="none",
    params=[
        param("api_key", STR, non_empty=True),
        param("block_id", STR, non_empty=True),
        param("page_size", INT, required=False, default=50, min_value=1, max_value=100),
        param("start_cursor", STR_OR_NONE, required=False),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.notion_get_block_children(ctx, **kwargs)
