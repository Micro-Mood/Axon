"""删除（归档）Notion 中的一个 block"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR
from ...handlers.base import RequestContext

tool = ToolDef(
    name="notion_delete_block",
    description="删除（归档）Notion 中的一个 block",
    lock="none",
    is_write=True,
    params=[
        param("api_key", STR, non_empty=True),
        param("block_id", STR, non_empty=True),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.notion_delete_block(ctx, **kwargs)
