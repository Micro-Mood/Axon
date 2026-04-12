"""抓取网页主要内容"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, STR_OR_NONE
from ...handlers.base import RequestContext

tool = ToolDef(
    name="fetch_webpage",
    description="抓取网页正文内容，自动去除 HTML 标签。可通过 query 参数定位相关段落",
    lock="none",
    params=[
        param("url", STR, non_empty=True),
        param("query", STR_OR_NONE, required=False),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.fetch_webpage(ctx, **kwargs)
