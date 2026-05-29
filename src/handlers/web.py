"""
Layer 4: Handlers — 网络操作

AI 工具:
  fetch_webpage → 抓取网页正文内容

依赖:
- Layer 1: core (MCPConfig, CacheManager)
- 第三方: aiohttp
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from html.parser import HTMLParser
from typing import Any

import aiohttp

from ..core.cache import CacheManager
from ..core.config import MCPConfig
from ..core.errors import InvalidParameterError, MCPError
from .base import BaseHandler, RequestContext

logger = logging.getLogger(__name__)

# 最大抓取字节数 (2 MB)
_MAX_FETCH_BYTES = 2 * 1024 * 1024

# 最大返回文本长度 (100K 字符)
_MAX_TEXT_LENGTH = 100_000

# 请求超时 (秒)
_REQUEST_TIMEOUT = 30

# 需要跳过内容的标签
_SKIP_TAGS = frozenset({
    "script", "style", "noscript", "svg", "math",
    "head", "meta", "link", "iframe", "object", "embed",
})


class _HTMLTextExtractor(HTMLParser):
    """从 HTML 中提取可读文本"""

    def __init__(self) -> None:
        super().__init__()
        self._pieces: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        # 块级标签前加换行
        if tag in ("p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6",
                    "li", "tr", "blockquote", "pre", "section", "article",
                    "header", "footer", "main", "nav", "aside", "dt", "dd"):
            self._pieces.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6",
                    "li", "tr", "blockquote", "pre", "section", "article"):
            self._pieces.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._pieces.append(data)

    def get_text(self) -> str:
        raw = "".join(self._pieces)
        # 合并连续空行为单个空行
        return re.sub(r"\n{3,}", "\n\n", raw).strip()


def _extract_text(html: str) -> str:
    """从 HTML 提取纯文本"""
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return parser.get_text()


def _find_relevant(text: str, query: str, context_chars: int = 3000) -> str:
    """
    在文本中查找与 query 相关的段落。
    返回 query 周围的上下文片段，用 ... 连接。
    如果找不到匹配，返回文本开头。
    """
    query_lower = query.lower()
    text_lower = text.lower()

    # 收集所有匹配位置
    positions: list[int] = []
    start = 0
    while True:
        idx = text_lower.find(query_lower, start)
        if idx == -1:
            break
        positions.append(idx)
        start = idx + 1

    if not positions:
        # 尝试按关键词拆分匹配
        keywords = [w for w in query_lower.split() if len(w) > 1]
        for kw in keywords:
            start = 0
            while True:
                idx = text_lower.find(kw, start)
                if idx == -1:
                    break
                positions.append(idx)
                start = idx + 1

    if not positions:
        # 无匹配，返回开头
        return text[:_MAX_TEXT_LENGTH]

    # 去重并排序
    positions = sorted(set(positions))

    # 提取上下文片段
    half = context_chars // 2
    snippets: list[str] = []
    total = 0

    for pos in positions:
        if total >= _MAX_TEXT_LENGTH:
            break
        lo = max(0, pos - half)
        hi = min(len(text), pos + half)
        snippet = text[lo:hi].strip()
        if snippet:
            snippets.append(snippet)
            total += len(snippet)

    return "\n\n...\n\n".join(snippets)


# ---- Notion API 常量 ----
_NOTION_API_BASE = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"
_NOTION_TIMEOUT = 30
_NOTION_RETRY_DELAYS = (0.5, 1.0, 2.0)


def _notion_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": _NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _rich_text_to_str(rich_texts: list) -> str:
    return "".join(rt.get("plain_text", "") for rt in rich_texts)


def _page_title(properties: dict) -> str:
    for v in properties.values():
        if isinstance(v, dict) and v.get("type") == "title":
            return _rich_text_to_str(v.get("title", []))
    return ""


def _block_to_text(block: dict) -> str:
    btype = block.get("type", "")
    inner = block.get(btype) or {}
    text = _rich_text_to_str(inner.get("rich_text", []))
    if btype == "divider":
        return "---"
    if btype == "code":
        lang = inner.get("language", "")
        return f"```{lang}\n{text}\n```"
    prefix = {
        "heading_1": "# ",
        "heading_2": "## ",
        "heading_3": "### ",
        "bulleted_list_item": "- ",
        "numbered_list_item": "1. ",
        "to_do": ("☑ " if inner.get("checked") else "☐ "),
        "quote": "> ",
        "callout": "> ",
    }.get(btype, "")
    return prefix + text if text else ""


class WebHandler(BaseHandler):
    """
    网络操作 handler

    方法: fetch_webpage, notion_search, notion_get_page,
          notion_query_database, notion_create_page, notion_append_blocks
    """

    async def fetch_webpage(
        self, ctx: RequestContext, **params: Any
    ) -> dict[str, Any]:
        """抓取网页正文内容"""
        url: str = params["url"]
        query: str | None = params.get("query")

        # 基本 URL 校验
        if not url.startswith(("http://", "https://")):
            raise InvalidParameterError("url", "必须以 http:// 或 https:// 开头")

        timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    url,
                    headers={"User-Agent": "Axon-MCP/1.0"},
                    max_redirects=5,
                ) as resp:
                    if resp.status != 200:
                        return {
                            "url": url,
                            "status": resp.status,
                            "error": f"HTTP {resp.status}",
                            "content": "",
                        }

                    content_type = resp.content_type or ""
                    raw = await resp.content.read(_MAX_FETCH_BYTES)

                    # 检测编码
                    encoding = resp.charset or "utf-8"
                    try:
                        body = raw.decode(encoding, errors="replace")
                    except (LookupError, UnicodeDecodeError):
                        body = raw.decode("utf-8", errors="replace")

        except aiohttp.ClientError as e:
            raise MCPError(f"网络请求失败: {e}") from e
        except TimeoutError:
            raise MCPError(f"请求超时 ({_REQUEST_TIMEOUT}s)") from None

        # HTML → 纯文本
        if "html" in content_type:
            text = _extract_text(body)
        else:
            text = body

        # 按 query 过滤相关段落
        if query:
            text = _find_relevant(text, query)

        # 截断
        truncated = len(text) > _MAX_TEXT_LENGTH
        if truncated:
            text = text[:_MAX_TEXT_LENGTH]

        return {
            "url": url,
            "status": 200,
            "content": text,
            "length": len(text),
            "truncated": truncated,
        }

    # ------------------------------------------------------------------ #
    #  Notion API                                                          #
    # ------------------------------------------------------------------ #

    async def _notion_request(
        self, method: str, path: str, api_key: str,
        body: dict | None = None,
    ) -> dict:
        """带指数退避重试的 Notion HTTP 请求"""
        url = f"{_NOTION_API_BASE}{path}"
        headers = _notion_headers(api_key)
        timeout = aiohttp.ClientTimeout(total=_NOTION_TIMEOUT)
        last_error: Exception | None = None

        for attempt in range(len(_NOTION_RETRY_DELAYS) + 1):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    req_func = getattr(session, method.lower())
                    kwargs: dict[str, Any] = {"headers": headers}
                    if body is not None:
                        kwargs["json"] = body
                    async with req_func(url, **kwargs) as resp:
                        if resp.status == 429:
                            if attempt < len(_NOTION_RETRY_DELAYS):
                                await asyncio.sleep(_NOTION_RETRY_DELAYS[attempt])
                                continue
                            raise MCPError("Notion API 超出速率限制，请稍后重试")
                        raw: dict = await resp.json()
                        if resp.status >= 400:
                            msg = (raw.get("message")
                                   or raw.get("code")
                                   or f"HTTP {resp.status}")
                            raise MCPError(f"Notion API 错误: {msg}")
                        return raw
            except aiohttp.ClientError as e:
                last_error = e
                if attempt < len(_NOTION_RETRY_DELAYS):
                    await asyncio.sleep(_NOTION_RETRY_DELAYS[attempt])
                    continue
                raise MCPError(f"Notion 请求失败: {last_error}") from last_error

        raise MCPError("Notion API 请求多次失败")  # pragma: no cover

    async def _notion_get(self, path: str, api_key: str) -> dict:
        return await self._notion_request("GET", path, api_key)

    async def _notion_post(self, path: str, api_key: str, body: dict) -> dict:
        return await self._notion_request("POST", path, api_key, body)

    async def _notion_patch(self, path: str, api_key: str, body: dict) -> dict:
        return await self._notion_request("PATCH", path, api_key, body)

    async def notion_search(
        self, ctx: RequestContext, **params: Any
    ) -> dict[str, Any]:
        """搜索 Notion 工作区"""
        api_key: str = params["api_key"]
        query: str = params["query"]
        filter_type: str | None = params.get("filter_type")
        page_size: int = int(params.get("page_size") or 10)

        body: dict = {"query": query, "page_size": page_size}
        if filter_type in ("page", "database"):
            body["filter"] = {"value": filter_type, "property": "object"}

        data = await self._notion_post("/search", api_key, body)

        results = []
        for item in data.get("results", []):
            obj_type = item.get("object")
            if obj_type == "database":
                title = _rich_text_to_str(item.get("title", []))
            else:
                title = _page_title(item.get("properties", {}))
            results.append({
                "id": item.get("id"),
                "type": obj_type,
                "title": title,
                "url": item.get("url"),
                "last_edited_time": item.get("last_edited_time"),
            })

        return {
            "results": results,
            "total": len(results),
            "has_more": data.get("has_more", False),
        }

    async def notion_get_page(
        self, ctx: RequestContext, **params: Any
    ) -> dict[str, Any]:
        """获取 Notion 页面元数据与正文（最多两层 block）"""
        api_key: str = params["api_key"]
        page_id: str = params["page_id"]
        include_content: bool = bool(params.get("include_content", True))

        page_data = await self._notion_get(f"/pages/{page_id}", api_key)
        props = page_data.get("properties", {})
        result: dict[str, Any] = {
            "id": page_data.get("id"),
            "title": _page_title(props),
            "url": page_data.get("url"),
            "created_time": page_data.get("created_time"),
            "last_edited_time": page_data.get("last_edited_time"),
            "archived": page_data.get("archived", False),
        }

        if include_content:
            blocks_data = await self._notion_get(
                f"/blocks/{page_id}/children", api_key
            )
            lines: list[str] = []
            for block in blocks_data.get("results", []):
                text = _block_to_text(block)
                if text:
                    lines.append(text)
                if block.get("has_children"):
                    bid = block.get("id")
                    try:
                        sub = await self._notion_get(
                            f"/blocks/{bid}/children", api_key
                        )
                        for sub_block in sub.get("results", []):
                            sub_text = _block_to_text(sub_block)
                            if sub_text:
                                lines.append("  " + sub_text)
                    except MCPError:
                        pass
            result["content"] = "\n".join(lines)

        return result

    async def notion_query_database(
        self, ctx: RequestContext, **params: Any
    ) -> dict[str, Any]:
        """查询 Notion 数据库"""
        api_key: str = params["api_key"]
        database_id: str = params["database_id"]
        filter_json: str | None = params.get("filter_json")
        sorts_json: str | None = params.get("sorts_json")
        page_size: int = int(params.get("page_size") or 20)

        body: dict = {"page_size": page_size}
        if filter_json:
            try:
                body["filter"] = json.loads(filter_json)
            except json.JSONDecodeError as e:
                raise InvalidParameterError(
                    "filter_json", f"JSON 格式错误: {e}"
                ) from e
        if sorts_json:
            try:
                body["sorts"] = json.loads(sorts_json)
            except json.JSONDecodeError as e:
                raise InvalidParameterError(
                    "sorts_json", f"JSON 格式错误: {e}"
                ) from e

        data = await self._notion_post(
            f"/databases/{database_id}/query", api_key, body
        )

        items = []
        for item in data.get("results", []):
            props = item.get("properties", {})
            items.append({
                "id": item.get("id"),
                "title": _page_title(props),
                "url": item.get("url"),
                "created_time": item.get("created_time"),
                "last_edited_time": item.get("last_edited_time"),
            })

        return {
            "items": items,
            "total": len(items),
            "has_more": data.get("has_more", False),
        }

    async def notion_create_page(
        self, ctx: RequestContext, **params: Any
    ) -> dict[str, Any]:
        """在 Notion 中创建新页面或数据库条目"""
        api_key: str = params["api_key"]
        parent_id: str = params["parent_id"]
        parent_type: str = params["parent_type"]
        title: str = params["title"]
        content: str | None = params.get("content")

        if parent_type not in ("page", "database"):
            raise InvalidParameterError(
                "parent_type", "必须是 'page' 或 'database'"
            )

        if parent_type == "database":
            # 查询数据库 schema 获取 title 属性名
            db_schema = await self._notion_get(
                f"/databases/{parent_id}", api_key
            )
            title_prop_name = "Name"  # Notion 默认名
            for prop_name, prop_def in db_schema.get("properties", {}).items():
                if prop_def.get("type") == "title":
                    title_prop_name = prop_name
                    break
            parent = {"database_id": parent_id}
            properties = {
                title_prop_name: {
                    "title": [{"type": "text", "text": {"content": title}}]
                }
            }
        else:
            parent = {"page_id": parent_id}
            properties = {
                "title": {
                    "title": [{"type": "text", "text": {"content": title}}]
                }
            }

        body: dict = {"parent": parent, "properties": properties}
        if content:
            body["children"] = [{
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": content}}]
                },
            }]

        data = await self._notion_post("/pages", api_key, body)
        return {
            "id": data.get("id"),
            "url": data.get("url"),
            "created_time": data.get("created_time"),
        }

    async def notion_append_blocks(
        self, ctx: RequestContext, **params: Any
    ) -> dict[str, Any]:
        """向 Notion 页面追加内容块"""
        api_key: str = params["api_key"]
        block_id: str = params["block_id"]
        content: str = params["content"]
        block_type: str = params.get("block_type") or "paragraph"

        _SUPPORTED = frozenset({
            "paragraph", "heading_1", "heading_2", "heading_3",
            "bulleted_list_item", "numbered_list_item", "quote", "code",
        })
        if block_type not in _SUPPORTED:
            block_type = "paragraph"

        rich_text = [{"type": "text", "text": {"content": content}}]
        if block_type == "code":
            child: dict = {
                "object": "block",
                "type": "code",
                "code": {"rich_text": rich_text, "language": "plain text"},
            }
        else:
            child = {
                "object": "block",
                "type": block_type,
                block_type: {"rich_text": rich_text},
            }

        data = await self._notion_patch(
            f"/blocks/{block_id}/children", api_key, {"children": [child]}
        )
        appended = data.get("results", [])
        return {
            "block_id": block_id,
            "appended_count": len(appended),
            "block_ids": [b.get("id") for b in appended],
        }
