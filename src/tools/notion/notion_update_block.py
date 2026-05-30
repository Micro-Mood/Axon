"""修改 Notion block 的文本内容或块类型"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, STR_OR_NONE
from ...handlers.base import RequestContext

tool = ToolDef(
    name="notion_update_block",
    description="修改 Notion block 的文本内容或块类型",
    lock="none",
    is_write=True,
    params=[
        param("api_key", STR, non_empty=True),
        param("block_id", STR, non_empty=True),
        param("content", STR, non_empty=True),
        param("block_type", STR_OR_NONE, required=False),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.notion_update_block(ctx, **kwargs)
