"""覆写文件内容"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR
from ...handlers.base import RequestContext

tool = ToolDef(
    name="write_file",
    description="覆写已存在文件的内容",
    lock="write",
    is_write=True,
    params=[
        param("path", STR, non_empty=True),
        param("content", STR),
        param("encoding", STR, required=False, default="utf-8"),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.write_file(ctx, **kwargs)
