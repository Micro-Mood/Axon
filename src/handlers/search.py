"""
Layer 4: Handlers — 搜索操作

提供三种搜索:
  find_files   — 按文件名/glob 模式搜索
  search_text  — 全局全文搜索文本/正则
  find_symbol  — 搜索代码符号（函数、类、变量定义）

依赖:
- Layer 1: core (MCPConfig, CacheManager, errors, Warning codes)
- Layer 2: platform (is_hidden, detect_file_encoding)
"""

from __future__ import annotations

import fnmatch
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from ..core.cache import CacheManager
from ..core.config import MCPConfig
from ..core.errors import (
    FileNotFoundError,
    InvalidParameterError,
    WARNING_PARTIAL_RESULT,
    WARNING_SLOW_OPERATION,
)
from ..platform import detect_file_encoding, is_hidden
from .base import BaseHandler, RequestContext

logger = logging.getLogger(__name__)

# 符号搜索正则（覆盖 Python, JS/TS, Java/C#, Go, Rust）
_SYMBOL_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "function": [
        re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\(", re.MULTILINE),                 # Python
        re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(", re.MULTILINE), # JS/TS
        re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*[<(]", re.MULTILINE),       # Rust
        re.compile(r"^\s*func\s+(\w+)\s*\(", re.MULTILINE),                               # Go
    ],
    "class": [
        re.compile(r"^\s*class\s+(\w+)\s*[:(]", re.MULTILINE),                            # Python/JS/TS
        re.compile(r"^\s*(?:pub\s+)?(?:abstract\s+)?class\s+(\w+)", re.MULTILINE),         # Java/C#
        re.compile(r"^\s*(?:pub\s+)?struct\s+(\w+)", re.MULTILINE),                        # Rust/Go
        re.compile(r"^\s*(?:pub\s+)?enum\s+(\w+)", re.MULTILINE),                          # Rust/TS
        re.compile(r"^\s*(?:pub\s+)?trait\s+(\w+)", re.MULTILINE),                         # Rust
        re.compile(r"^\s*interface\s+(\w+)", re.MULTILINE),                                # TS/Java
    ],
    "variable": [
        re.compile(r"^(\w+)\s*=\s*", re.MULTILINE),                                       # Python
        re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*[=:]", re.MULTILINE),   # JS/TS
    ],
}

# 二进制文件扩展名（跳过搜索）
_BINARY_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".mp3", ".mp4", ".avi", ".mov", ".wav", ".flac",
    ".zip", ".gz", ".tar", ".rar", ".7z", ".bz2",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".exe", ".dll", ".so", ".dylib", ".o", ".obj",
    ".pyc", ".pyo", ".class", ".wasm",
    ".db", ".sqlite", ".sqlite3",
    ".bin", ".dat", ".pak",
})

# 安全限制
_MAX_REGEX_LENGTH = 10000
_PER_FILE_TIMEOUT_S = 5.0


class SearchHandler(BaseHandler):
    """文件/内容/符号搜索 handler"""

    # ═══════════════════════════════════════════════════
    #  find_files — 文件名搜索
    # ═══════════════════════════════════════════════════

    async def find_files(
        self,
        ctx: RequestContext,
        pattern: str,
        root: Path | None = None,
        recursive: bool = True,
        file_types: list[str] | None = None,
        include_hidden: bool = False,
        max_results: int | None = None,
    ) -> dict[str, Any]:
        """
        按文件名/glob 模式搜索

        Args:
            pattern: glob 模式（如 "*.py", "test_*"）
            root: 搜索根目录，None 则使用 workspace
            recursive: 是否递归搜索
            file_types: 文件扩展名过滤（如 [".py", ".js"]）
            include_hidden: 是否包含隐藏文件
            max_results: 最大返回数量

        Returns:
            {pattern, root, matches: [{path, name, size, mtime}], total, truncated}
        """
        search_root = root or self.workspace
        limit = max_results or self.config.performance.max_search_results

        if not search_root.exists():
            raise FileNotFoundError(
                f"搜索根目录不存在: {search_root}",
                details={"root": str(search_root)},
            )

        t0 = time.monotonic()
        matches: list[dict[str, Any]] = []
        total = 0

        iterator = search_root.rglob(pattern) if recursive else search_root.glob(pattern)

        for item in iterator:
            if not item.is_file():
                continue
            if not include_hidden and is_hidden(item):
                continue
            if file_types and item.suffix.lower() not in file_types:
                continue

            total += 1
            if len(matches) >= limit:
                continue

            try:
                s = item.stat()
            except OSError:
                continue

            matches.append({
                "path": str(item),
                "name": item.name,
                "relative": str(item.relative_to(search_root)),
                "size": s.st_size,
            })

        elapsed_ms = (time.monotonic() - t0) * 1000
        truncated = total > limit

        if truncated:
            ctx.warn(
                WARNING_PARTIAL_RESULT,
                f"结果已截断: 共 {total} 项，仅返回 {limit} 项",
                total=total, returned=limit,
            )
        if elapsed_ms > 5000:
            ctx.warn(
                WARNING_SLOW_OPERATION,
                f"文件搜索耗时 {elapsed_ms:.0f}ms",
                duration_ms=round(elapsed_ms),
            )

        return {
            "pattern": pattern,
            "root": str(search_root),
            "matches": matches,
            "total": total,
            "truncated": truncated,
            "duration_ms": round(elapsed_ms),
        }

    # ═══════════════════════════════════════════════════
    #  search_text — 全局全文搜索
    # ═══════════════════════════════════════════════════

    async def search_text(
        self,
        ctx: RequestContext,
        query: str,
        root: Path | None = None,
        file_pattern: str = "*",
        case_sensitive: bool = False,
        is_regex: bool = False,
        context_lines: int = 2,
        include_hidden: bool = False,
        max_results: int | None = None,
    ) -> dict[str, Any]:
        """
        在文件内容中搜索文本/正则

        Args:
            query: 搜索文本或正则表达式
            root: 搜索根目录
            file_pattern: 文件名过滤 glob（如 "*.py"）
            case_sensitive: 是否区分大小写
            is_regex: query 是否为正则表达式
            context_lines: 上下文行数
            include_hidden: 是否搜索隐藏文件
            max_results: 最大匹配文件数

        Returns:
            {query, root, matches: [{path, hits: [{line, content, context}]}],
             total_files, total_hits, truncated}
        """
        search_root = root or self.workspace
        limit = max_results or self.config.performance.max_search_results

        if not search_root.exists():
            raise FileNotFoundError(
                f"搜索根目录不存在: {search_root}",
                details={"root": str(search_root)},
            )

        # 编译搜索模式
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            if is_regex:
                if len(query) > _MAX_REGEX_LENGTH:
                    raise InvalidParameterError(
                        f"正则表达式过长: {len(query)} 字符（上限 {_MAX_REGEX_LENGTH}）",
                        details={"length": len(query), "limit": _MAX_REGEX_LENGTH},
                    )
                compiled = re.compile(query, flags)
            else:
                compiled = re.compile(re.escape(query), flags)
        except re.error as e:
            raise InvalidParameterError(
                f"无效的正则表达式: {query}",
                details={"query": query, "error": str(e)},
                cause=e,
            )

        t0 = time.monotonic()
        matches: list[dict[str, Any]] = []
        total_files = 0
        total_hits = 0
        files_with_hits = 0

        # 遍历文件
        for item in search_root.rglob(file_pattern):
            if not item.is_file():
                continue
            if not include_hidden and is_hidden(item):
                continue
            if item.suffix.lower() in _BINARY_EXTENSIONS:
                continue

            total_files += 1

            # 单文件时间预算
            file_start = time.monotonic()

            # 读取文件内容 — 自动检测编码
            try:
                head = item.read_bytes()[:8192]
                file_enc = detect_file_encoding(head)
                content = item.read_text(encoding=file_enc, errors="replace")
            except (OSError, PermissionError):
                continue

            lines = content.splitlines()
            hits: list[dict[str, Any]] = []

            for line_num, line_text in enumerate(lines, start=1):
                if compiled.search(line_text):
                    # 提取上下文
                    ctx_start = max(0, line_num - 1 - context_lines)
                    ctx_end = min(len(lines), line_num + context_lines)
                    context = [
                        {"line": ctx_start + i + 1, "content": lines[ctx_start + i]}
                        for i in range(ctx_end - ctx_start)
                    ]

                    hits.append({
                        "line": line_num,
                        "content": line_text,
                        "context": context,
                    })
                    total_hits += 1

                # 单文件超时保护
                if time.monotonic() - file_start > _PER_FILE_TIMEOUT_S:
                    break

            if hits:
                files_with_hits += 1
                if files_with_hits <= limit:
                    matches.append({
                        "path": str(item),
                        "relative": str(item.relative_to(search_root)),
                        "hits": hits,
                    })

        elapsed_ms = (time.monotonic() - t0) * 1000
        truncated = files_with_hits > limit

        if truncated:
            ctx.warn(
                WARNING_PARTIAL_RESULT,
                f"匹配文件已截断: 共 {files_with_hits} 文件，仅返回 {limit} 文件",
                total_files_matched=files_with_hits, returned=limit,
            )
        if elapsed_ms > 5000:
            ctx.warn(
                WARNING_SLOW_OPERATION,
                f"内容搜索耗时 {elapsed_ms:.0f}ms",
                duration_ms=round(elapsed_ms),
            )

        return {
            "query": query,
            "root": str(search_root),
            "matches": matches,
            "total_files_searched": total_files,
            "total_files_matched": files_with_hits,
            "total_hits": total_hits,
            "truncated": truncated,
            "duration_ms": round(elapsed_ms),
        }

    # ═══════════════════════════════════════════════════
    #  find_symbol — 代码符号搜索
    # ═══════════════════════════════════════════════════

    async def find_symbol(
        self,
        ctx: RequestContext,
        symbol: str,
        root: Path | None = None,
        symbol_type: str | None = None,
        file_pattern: str = "*",
        include_hidden: bool = False,
        max_results: int | None = None,
    ) -> dict[str, Any]:
        """
        搜索代码符号（函数、类、变量定义）

        Args:
            symbol: 符号名（支持正则）
            root: 搜索根目录
            symbol_type: 限定类型 "function" / "class" / "variable"，None 搜全部
            file_pattern: 文件名过滤
            include_hidden: 是否搜索隐藏文件
            max_results: 最大返回数量

        Returns:
            {symbol, matches: [{path, name, type, line, context}], total, truncated}
        """
        search_root = root or self.workspace
        limit = max_results or self.config.performance.max_search_results

        if not search_root.exists():
            raise FileNotFoundError(
                f"搜索根目录不存在: {search_root}",
                details={"root": str(search_root)},
            )

        # 确定搜索哪些符号类型
        if symbol_type:
            if symbol_type not in _SYMBOL_PATTERNS:
                raise InvalidParameterError(
                    f"不支持的符号类型: {symbol_type}",
                    details={
                        "symbol_type": symbol_type,
                        "supported": list(_SYMBOL_PATTERNS.keys()),
                    },
                )
            types_to_search = {symbol_type: _SYMBOL_PATTERNS[symbol_type]}
        else:
            types_to_search = _SYMBOL_PATTERNS

        # 编译符号名匹配（限制长度防 ReDoS）
        if len(symbol) > _MAX_REGEX_LENGTH:
            raise InvalidParameterError(
                f"符号名过长: {len(symbol)} 字符（上限 {_MAX_REGEX_LENGTH}）",
                details={"length": len(symbol), "limit": _MAX_REGEX_LENGTH},
            )
        try:
            symbol_re = re.compile(symbol, re.IGNORECASE)
        except re.error:
            # 如果不是合法正则，当作纯文本
            symbol_re = re.compile(re.escape(symbol), re.IGNORECASE)

        t0 = time.monotonic()
        matches: list[dict[str, Any]] = []
        total = 0

        for item in search_root.rglob(file_pattern):
            if not item.is_file():
                continue
            if not include_hidden and is_hidden(item):
                continue
            if item.suffix.lower() in _BINARY_EXTENSIONS:
                continue

            try:
                head = item.read_bytes()[:8192]
                file_enc = detect_file_encoding(head)
                content = item.read_text(encoding=file_enc, errors="replace")
            except (OSError, PermissionError):
                continue

            lines = content.splitlines()

            for type_name, patterns in types_to_search.items():
                for pattern in patterns:
                    for m in pattern.finditer(content):
                        name = m.group(1)
                        if not symbol_re.search(name):
                            continue

                        # 计算行号
                        line_num = content[:m.start()].count("\n") + 1

                        # 上下文（前后 2 行）
                        ctx_start = max(0, line_num - 3)
                        ctx_end = min(len(lines), line_num + 2)
                        context = "\n".join(lines[ctx_start:ctx_end])

                        total += 1
                        if len(matches) < limit:
                            matches.append({
                                "path": str(item),
                                "relative": str(item.relative_to(search_root)),
                                "name": name,
                                "type": type_name,
                                "line": line_num,
                                "context": context,
                            })

        elapsed_ms = (time.monotonic() - t0) * 1000
        truncated = total > limit

        if truncated:
            ctx.warn(
                WARNING_PARTIAL_RESULT,
                f"符号搜索结果已截断: 共 {total} 个，仅返回 {limit} 个",
                total=total, returned=limit,
            )
        if elapsed_ms > 5000:
            ctx.warn(
                WARNING_SLOW_OPERATION,
                f"符号搜索耗时 {elapsed_ms:.0f}ms",
                duration_ms=round(elapsed_ms),
            )

        return {
            "symbol": symbol,
            "root": str(search_root),
            "matches": matches,
            "total": total,
            "truncated": truncated,
            "duration_ms": round(elapsed_ms),
        }
