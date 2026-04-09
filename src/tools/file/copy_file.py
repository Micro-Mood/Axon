"""复制文件"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, BOOL
from ...handlers.base import RequestContext

tool = ToolDef(
    name="copy_file",
    description="复制文件到目标路径",
    lock="write_dual",
    is_write=True,
    params=[
        param("source", STR, non_empty=True),
        param("dest", STR, non_empty=True),
        param("overwrite", BOOL, required=False, default=False),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.copy_file(ctx, **kwargs)
