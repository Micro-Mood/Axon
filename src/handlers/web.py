"""
Layer 4: Handlers — 网络操作

AI 工具:
  fetch_webpage → 抓取网页正文内容

依赖:
- Layer 1: core (MCPConfig, CacheManager)
- 第三方: aiohttp
"""

from __future__ import annotations

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


class WebHandler(BaseHandler):
    """
    网络操作 handler

    方法: fetch_webpage
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
                    ssl=False,
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
            raise MCPError(-32000, f"网络请求失败: {e}") from e
        except TimeoutError:
            raise MCPError(-32000, f"请求超时 ({_REQUEST_TIMEOUT}s)") from None

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
