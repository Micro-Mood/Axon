"""
Layer 4: Handlers — Notion API

AI 工具:
  notion_search          → 搜索页面/数据库
  notion_get_page        → 读取页面（支持分页）
  notion_get_block_children → 分页读取 block 子节点
  notion_query_database  → 查询数据库
  notion_get_comments    → 获取评论
  notion_list_users      → 列出工作区成员
  notion_create_page     → 创建页面
  notion_update_page     → 更新页面属性/标题
  notion_archive_page    → 归档页面（移入回收站）
  notion_append_blocks   → 追加 block
  notion_update_block    → 更新 block 内容
  notion_delete_block    → 删除 block
  notion_create_database → 创建数据库
  notion_update_database → 更新数据库结构
  notion_create_comment  → 添加评论

依赖:
- Layer 1: core (MCPConfig, CacheManager)
- 第三方: aiohttp
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp

from ..core.errors import InvalidParameterError, MCPError
from .base import BaseHandler, RequestContext

logger = logging.getLogger(__name__)

# ---- Notion API 常量 ----
_NOTION_API_BASE = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"
_NOTION_TIMEOUT = 30
_NOTION_RETRY_DELAYS = (0.5, 1.0, 2.0)

# 默认最大 block 数（防止超长页面导致响应过大）
_MAX_BLOCKS_DEFAULT = 100
_MAX_BLOCKS_LIMIT = 500

# Notion API page_size 上限
_NOTION_PAGE_SIZE_MAX = 100


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


class NotionHandler(BaseHandler):
    """
    Notion API handler

    方法: notion_search, notion_get_page, notion_get_block_children,
          notion_query_database, notion_get_comments, notion_list_users,
          notion_create_page, notion_update_page, notion_archive_page,
          notion_append_blocks, notion_update_block, notion_delete_block,
          notion_create_database, notion_update_database, notion_create_comment
    """

    # ------------------------------------------------------------------ #
    #  HTTP 基础                                                           #
    # ------------------------------------------------------------------ #

    async def _notion_request(
        self,
        method: str,
        path: str,
        api_key: str,
        body: dict | None = None,
        qs: dict | None = None,
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
                    if qs is not None:
                        kwargs["params"] = qs
                    async with req_func(url, **kwargs) as resp:
                        if resp.status == 429:
                            if attempt < len(_NOTION_RETRY_DELAYS):
                                await asyncio.sleep(_NOTION_RETRY_DELAYS[attempt])
                                continue
                            raise MCPError("Notion API 超出速率限制，请稍后重试")
                        raw: dict = await resp.json()
                        if resp.status >= 400:
                            msg = (
                                raw.get("message")
                                or raw.get("code")
                                or f"HTTP {resp.status}"
                            )
                            raise MCPError(f"Notion API 错误: {msg}")
                        return raw
            except aiohttp.ClientError as e:
                last_error = e
                if attempt < len(_NOTION_RETRY_DELAYS):
                    await asyncio.sleep(_NOTION_RETRY_DELAYS[attempt])
                    continue
                raise MCPError(f"Notion 请求失败: {last_error}") from last_error

        raise MCPError("Notion API 请求多次失败")  # pragma: no cover

    async def _notion_get(
        self, path: str, api_key: str, qs: dict | None = None
    ) -> dict:
        return await self._notion_request("GET", path, api_key, qs=qs)

    async def _notion_post(self, path: str, api_key: str, body: dict) -> dict:
        return await self._notion_request("POST", path, api_key, body)

    async def _notion_patch(self, path: str, api_key: str, body: dict) -> dict:
        return await self._notion_request("PATCH", path, api_key, body)

    async def _notion_delete(self, path: str, api_key: str) -> dict:
        return await self._notion_request("DELETE", path, api_key)

    # ------------------------------------------------------------------ #
    #  读取工具                                                            #
    # ------------------------------------------------------------------ #

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
        """获取 Notion 页面元数据与正文（支持分页，防止超大页面）"""
        api_key: str = params["api_key"]
        page_id: str = params["page_id"]
        include_content: bool = bool(params.get("include_content", True))
        max_blocks: int = min(
            int(params.get("max_blocks") or _MAX_BLOCKS_DEFAULT),
            _MAX_BLOCKS_LIMIT,
        )
        start_cursor: str | None = params.get("start_cursor") or None

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
            lines: list[str] = []
            block_count = 0
            has_more = False
            next_cursor: str | None = None

            req_qs: dict = {"page_size": min(max_blocks, _NOTION_PAGE_SIZE_MAX)}
            if start_cursor:
                req_qs["start_cursor"] = start_cursor

            blocks_data = await self._notion_get(
                f"/blocks/{page_id}/children", api_key, qs=req_qs
            )
            for block in blocks_data.get("results", []):
                if block_count >= max_blocks:
                    has_more = True
                    break
                text = _block_to_text(block)
                if text:
                    lines.append(text)
                block_count += 1

                if block.get("has_children") and block_count < max_blocks:
                    bid = block.get("id")
                    try:
                        sub = await self._notion_get(
                            f"/blocks/{bid}/children",
                            api_key,
                            qs={"page_size": min(50, max_blocks - block_count)},
                        )
                        for sub_block in sub.get("results", []):
                            if block_count >= max_blocks:
                                has_more = True
                                break
                            sub_text = _block_to_text(sub_block)
                            if sub_text:
                                lines.append("  " + sub_text)
                            block_count += 1
                    except MCPError:
                        pass

            if not has_more and blocks_data.get("has_more"):
                has_more = True
                next_cursor = blocks_data.get("next_cursor")

            result["content"] = "\n".join(lines)
            result["block_count"] = block_count
            result["has_more"] = has_more
            if next_cursor:
                result["next_cursor"] = next_cursor
            if has_more:
                result["hint"] = (
                    f"页面内容已截断（已获取 {block_count} 个 block），"
                    "使用 notion_get_block_children 配合 start_cursor 分页续读"
                )

        return result

    async def notion_get_block_children(
        self, ctx: RequestContext, **params: Any
    ) -> dict[str, Any]:
        """分页获取 block 子节点（用于处理超大页面内容）"""
        api_key: str = params["api_key"]
        block_id: str = params["block_id"]
        page_size: int = min(
            int(params.get("page_size") or 50), _NOTION_PAGE_SIZE_MAX
        )
        start_cursor: str | None = params.get("start_cursor") or None

        req_qs: dict = {"page_size": page_size}
        if start_cursor:
            req_qs["start_cursor"] = start_cursor

        data = await self._notion_get(
            f"/blocks/{block_id}/children", api_key, qs=req_qs
        )

        blocks = []
        lines: list[str] = []
        for block in data.get("results", []):
            text = _block_to_text(block)
            blocks.append({
                "id": block.get("id"),
                "type": block.get("type"),
                "text": text,
                "has_children": block.get("has_children", False),
            })
            if text:
                lines.append(text)

        result: dict[str, Any] = {
            "block_id": block_id,
            "blocks": blocks,
            "content": "\n".join(lines),
            "count": len(blocks),
            "has_more": data.get("has_more", False),
        }
        if data.get("next_cursor"):
            result["next_cursor"] = data["next_cursor"]
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

    async def notion_get_comments(
        self, ctx: RequestContext, **params: Any
    ) -> dict[str, Any]:
        """获取 Notion 页面/block 的评论"""
        api_key: str = params["api_key"]
        block_id: str = params["block_id"]
        page_size: int = min(
            int(params.get("page_size") or 20), _NOTION_PAGE_SIZE_MAX
        )

        data = await self._notion_get(
            "/comments",
            api_key,
            qs={"block_id": block_id, "page_size": page_size},
        )

        comments = []
        for item in data.get("results", []):
            comments.append({
                "id": item.get("id"),
                "text": _rich_text_to_str(item.get("rich_text", [])),
                "created_by": item.get("created_by", {}).get("id"),
                "created_time": item.get("created_time"),
            })

        return {
            "comments": comments,
            "total": len(comments),
            "has_more": data.get("has_more", False),
        }

    async def notion_list_users(
        self, ctx: RequestContext, **params: Any
    ) -> dict[str, Any]:
        """列出 Notion 工作区成员"""
        api_key: str = params["api_key"]
        page_size: int = min(
            int(params.get("page_size") or 20), _NOTION_PAGE_SIZE_MAX
        )

        data = await self._notion_get(
            "/users", api_key, qs={"page_size": page_size}
        )

        users = []
        for item in data.get("results", []):
            users.append({
                "id": item.get("id"),
                "name": item.get("name"),
                "type": item.get("type"),
                "avatar_url": item.get("avatar_url"),
            })

        return {
            "users": users,
            "total": len(users),
            "has_more": data.get("has_more", False),
        }

    # ------------------------------------------------------------------ #
    #  写入工具                                                            #
    # ------------------------------------------------------------------ #

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
            db_schema = await self._notion_get(f"/databases/{parent_id}", api_key)
            title_prop_name = "Name"
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

    async def notion_update_page(
        self, ctx: RequestContext, **params: Any
    ) -> dict[str, Any]:
        """更新 Notion 页面标题或属性"""
        api_key: str = params["api_key"]
        page_id: str = params["page_id"]
        title: str | None = params.get("title")
        properties_json: str | None = params.get("properties_json")

        properties: dict = {}
        if title is not None:
            properties["title"] = {
                "title": [{"type": "text", "text": {"content": title}}]
            }
        if properties_json:
            try:
                extra = json.loads(properties_json)
                if isinstance(extra, dict):
                    properties.update(extra)
            except json.JSONDecodeError as e:
                raise InvalidParameterError(
                    "properties_json", f"JSON 格式错误: {e}"
                ) from e

        if not properties:
            raise InvalidParameterError(
                "title", "title 和 properties_json 至少提供一个"
            )

        data = await self._notion_patch(
            f"/pages/{page_id}", api_key, {"properties": properties}
        )
        return {
            "id": data.get("id"),
            "url": data.get("url"),
            "last_edited_time": data.get("last_edited_time"),
        }

    async def notion_archive_page(
        self, ctx: RequestContext, **params: Any
    ) -> dict[str, Any]:
        """将 Notion 页面归档（移入回收站）"""
        api_key: str = params["api_key"]
        page_id: str = params["page_id"]

        data = await self._notion_patch(
            f"/pages/{page_id}", api_key, {"archived": True}
        )
        return {
            "id": data.get("id"),
            "archived": data.get("archived", True),
            "url": data.get("url"),
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

    async def notion_update_block(
        self, ctx: RequestContext, **params: Any
    ) -> dict[str, Any]:
        """更新 Notion block 内容"""
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
            block_body: dict = {
                "code": {"rich_text": rich_text, "language": "plain text"}
            }
        else:
            block_body = {block_type: {"rich_text": rich_text}}

        data = await self._notion_patch(f"/blocks/{block_id}", api_key, block_body)
        return {
            "id": data.get("id"),
            "type": data.get("type"),
            "last_edited_time": data.get("last_edited_time"),
        }

    async def notion_delete_block(
        self, ctx: RequestContext, **params: Any
    ) -> dict[str, Any]:
        """删除（归档）Notion block"""
        api_key: str = params["api_key"]
        block_id: str = params["block_id"]

        data = await self._notion_delete(f"/blocks/{block_id}", api_key)
        return {
            "id": data.get("id"),
            "archived": data.get("archived", True),
        }

    async def notion_create_database(
        self, ctx: RequestContext, **params: Any
    ) -> dict[str, Any]:
        """在 Notion 页面下创建新的内联数据库"""
        api_key: str = params["api_key"]
        parent_id: str = params["parent_id"]
        title: str = params["title"]
        properties_json: str | None = params.get("properties_json")

        properties: dict = {"Name": {"title": {}}}
        if properties_json:
            try:
                extra = json.loads(properties_json)
                if isinstance(extra, dict):
                    properties.update(extra)
            except json.JSONDecodeError as e:
                raise InvalidParameterError(
                    "properties_json", f"JSON 格式错误: {e}"
                ) from e

        body: dict = {
            "parent": {"page_id": parent_id},
            "title": [{"type": "text", "text": {"content": title}}],
            "properties": properties,
        }
        data = await self._notion_post("/databases", api_key, body)
        return {
            "id": data.get("id"),
            "url": data.get("url"),
            "created_time": data.get("created_time"),
        }

    async def notion_update_database(
        self, ctx: RequestContext, **params: Any
    ) -> dict[str, Any]:
        """更新 Notion 数据库标题或属性结构"""
        api_key: str = params["api_key"]
        database_id: str = params["database_id"]
        title: str | None = params.get("title")
        properties_json: str | None = params.get("properties_json")

        body: dict = {}
        if title is not None:
            body["title"] = [{"type": "text", "text": {"content": title}}]
        if properties_json:
            try:
                body["properties"] = json.loads(properties_json)
            except json.JSONDecodeError as e:
                raise InvalidParameterError(
                    "properties_json", f"JSON 格式错误: {e}"
                ) from e

        if not body:
            raise InvalidParameterError(
                "title", "title 和 properties_json 至少提供一个"
            )

        data = await self._notion_patch(
            f"/databases/{database_id}", api_key, body
        )
        return {
            "id": data.get("id"),
            "url": data.get("url"),
            "last_edited_time": data.get("last_edited_time"),
        }

    async def notion_create_comment(
        self, ctx: RequestContext, **params: Any
    ) -> dict[str, Any]:
        """在 Notion 页面/block 上添加评论"""
        api_key: str = params["api_key"]
        block_id: str = params["block_id"]
        content: str = params["content"]

        body = {
            "parent": {"page_id": block_id},
            "rich_text": [{"type": "text", "text": {"content": content}}],
        }
        data = await self._notion_post("/comments", api_key, body)
        return {
            "id": data.get("id"),
            "created_time": data.get("created_time"),
        }
