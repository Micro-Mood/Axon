"""清空缓存"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR_OR_NONE
from ...handlers.base import RequestContext

tool = ToolDef(
    name="clear_cache",
    description="清空缓存（可指定桶）",
    lock="none",
    params=[
        param("bucket", STR_OR_NONE, required=False),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.clear_cache(ctx, **kwargs)
