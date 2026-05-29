"""向 Notion 页面追加内容块"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, STR_OR_NONE
from ...handlers.base import RequestContext

tool = ToolDef(
    name="notion_append_blocks",
    description="向 Notion 页面追加内容块（段落、标题等）",
    lock="none",
    is_write=True,
    params=[
        param("api_key", STR, non_empty=True),
        param("block_id", STR, non_empty=True),
        param("content", STR, non_empty=True),
        param("block_type", STR_OR_NONE, required=False),  # "paragraph"|"heading_1"|...
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.notion_append_blocks(ctx, **kwargs)
