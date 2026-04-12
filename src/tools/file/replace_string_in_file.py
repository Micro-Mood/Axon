"""替换文件中匹配的文本"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR
from ...handlers.base import RequestContext

tool = ToolDef(
    name="replace_string_in_file",
    description="在文件中查找 old_string 并替换为 new_string，old_string 必须精确匹配且在文件中唯一",
    lock="write",
    is_write=True,
    params=[
        param("path", STR, non_empty=True),
        param("old_string", STR, non_empty=True),
        param("new_string", STR),
        param("encoding", STR, required=False, default="utf-8"),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.replace_string_in_file(ctx, **kwargs)
