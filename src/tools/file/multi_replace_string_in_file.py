"""批量替换文件中的文本"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, LIST
from ...handlers.base import RequestContext

tool = ToolDef(
    name="multi_replace_string_in_file",
    description="批量文本替换，replacements 数组中每项包含 path/old_string/new_string",
    lock="write",
    is_write=True,
    params=[
        param("replacements", LIST, non_empty=True),
        param("encoding", STR, required=False, default="utf-8"),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.multi_replace_string_in_file(ctx, **kwargs)
