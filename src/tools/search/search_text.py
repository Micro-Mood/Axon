"""在文件内容中搜索文本/正则（全局全文搜索）"""
from __future__ import annotations

from typing import Any

from .. import ToolDef, param, STR, STR_OR_NONE, BOOL, INT, INT_OR_NONE
from ...handlers.base import RequestContext

tool = ToolDef(
    name="search_text",
    description="在工作区中全局搜索文本或正则表达式，返回匹配的文件、行号和上下文",
    lock="none",
    params=[
        param("query", STR, non_empty=True),
        param("root", STR_OR_NONE, required=False),
        param("file_pattern", STR, required=False, default="*"),
        param("case_sensitive", BOOL, required=False, default=False),
        param("is_regex", BOOL, required=False, default=False),
        param("context_lines", INT, required=False, default=2, min_value=0, max_value=50),
        param("include_hidden", BOOL, required=False, default=False),
        param("max_results", INT_OR_NONE, required=False, min_value=1),
    ],
)


async def execute(handler: Any, ctx: RequestContext, **kwargs: Any) -> dict[str, Any]:
    return await handler.search_text(ctx, **kwargs)
