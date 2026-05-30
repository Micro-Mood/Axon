"""读取 Notion 页面内容（支持分页，超大页面用 notion_get_block_children 续读）"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, STR_OR_NONE, BOOL, INT
from ...handlers.base import RequestContext

tool = ToolDef(
    name="notion_get_page",
    description=(
        "获取 Notion 页面的元数据和正文内容。"
        "超大页面时设置 max_blocks 限制，使用 start_cursor + notion_get_block_children 分页续读"
    ),
    lock="none",
    params=[
        param("api_key", STR, non_empty=True),
        param("page_id", STR, non_empty=True),
        param("include_content", BOOL, required=False, default=True),
        param("max_blocks", INT, required=False, default=100, min_value=1, max_value=500),
        param("start_cursor", STR_OR_NONE, required=False),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.notion_get_page(ctx, **kwargs)
