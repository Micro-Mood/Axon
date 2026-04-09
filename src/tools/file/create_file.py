"""创建文件"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, BOOL
from ...handlers.base import RequestContext

tool = ToolDef(
    name="create_file",
    description="创建文件，支持指定编码和覆写",
    lock="write",
    is_write=True,
    params=[
        param("path", STR, non_empty=True),
        param("content", STR, required=False, default=""),
        param("encoding", STR, required=False, default="utf-8"),
        param("overwrite", BOOL, required=False, default=False),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.create_file(ctx, **kwargs)
