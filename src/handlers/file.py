"""
Layer 4: Handlers — 文件操作

所有文件/目录的 CRUD 操作。
安全校验（路径检查、权限检查）由 Middleware 层自动完成，
handler 收到的 path 已是经过校验的绝对路径。

方法分类:
  读取: read_file, stat_path, exists, list_directory
  写入: create_file, write_file, create_directory
  修改: replace_range, insert_text, delete_range, apply_patch
  移动/复制/删除: move_file, copy_file, delete_file, move_directory, delete_directory

依赖:
- Layer 1: core (MCPConfig, CacheManager, errors, Warning codes)
- Layer 2: platform (is_hidden, get_file_attributes_from_stat, detect_file_encoding)
"""

from __future__ import annotations

import difflib
import fnmatch
import logging
import os
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiofiles
import aiofiles.os

from ..core.cache import CacheManager
from ..core.config import MCPConfig
from ..core.errors import (
    ConcurrentModificationError,
    EncodingError,
    FileNotFoundError,
    InvalidParameterError,
    PatchApplyError,
    PermissionDeniedError,
    SizeLimitExceededError,
    Warning,
    WARNING_LARGE_FILE,
    WARNING_PARTIAL_RESULT,
)
from ..platform import (
    detect_file_encoding,
    get_file_attributes_from_stat,
    is_hidden,
)
from .base import BaseHandler, RequestContext

logger = logging.getLogger(__name__)


class FileHandler(BaseHandler):
    """
    统一文件操作 handler

    所有方法的第一个参数是 RequestContext，供中间件使用。
    路径参数 (path / source / dest) 由中间件校验后写入
    ctx.validated_paths，handler 从中取用。
    """

    # ═══════════════════════════════════════════════════
    #  读取类
    # ═══════════════════════════════════════════════════

    async def read_file(
        self,
        ctx: RequestContext,
        path: Path,
        encoding: str | None = None,
        line_range: tuple[int, int] | None = None,
        max_size: int | None = None,
    ) -> dict[str, Any]:
        """
        读取文件内容

        Args:
            path: 绝对路径（已校验）
            encoding: 编码，None 则自动检测
            line_range: (start, end) 行号范围，1-based，闭区间
            max_size: 最大读取字节数，None 使用配置默认值

        Returns:
            {path, content, encoding, size, lines, truncated}
        """
        if not path.exists():
            raise FileNotFoundError(
                f"文件不存在: {path}",
                details={"path": str(path)},
            )

        file_stat = path.stat()
        file_size = file_stat.st_size
        limit_bytes = max_size or self.config.security.max_file_size_mb * 1024 * 1024

        # 大文件警告
        if file_size > limit_bytes:
            raise SizeLimitExceededError(
                f"文件过大: {file_size} 字节",
                details={"path": str(path), "size": file_size, "limit": limit_bytes},
            )
        if file_size > 1024 * 1024:  # > 1MB 警告
            ctx.warn(WARNING_LARGE_FILE, f"文件较大: {file_size} 字节", size=file_size)

        # 检测编码
        if encoding is None:
            # 读取文件头部用于编码检测
            head = path.read_bytes()[:4096]
            encoding = detect_file_encoding(head)

        # 读取
        try:
            async with aiofiles.open(path, mode="r", encoding=encoding) as f:
                content = await f.read()
        except UnicodeDecodeError as e:
            raise EncodingError(
                f"文件解码失败 (encoding={encoding}): {e}",
                details={"path": str(path), "encoding": encoding},
                cause=e,
                suggestion="尝试指定正确的 encoding 参数",
            )

        lines = content.splitlines(keepends=True)
        total_lines = len(lines)
        truncated = False

        # 行号范围截取
        if line_range is not None:
            start, end = line_range
            if start < 1:
                start = 1
            if end > total_lines:
                end = total_lines
            lines = lines[start - 1 : end]
            content = "".join(lines)
            truncated = True

        # 缓存元数据
        self.cache.set("metadata", str(path), {
            "size": file_size,
            "lines": total_lines,
            "mtime": file_stat.st_mtime,
        })

        return {
            "path": str(path),
            "content": content,
            "encoding": encoding,
            "size": file_size,
            "lines": total_lines,
            "truncated": truncated,
        }

    async def stat_path(
        self,
        ctx: RequestContext,
        path: Path,
        follow_symlinks: bool = True,
    ) -> dict[str, Any]:
        """
        获取文件/目录元信息

        Returns:
            {path, exists, type, size, permissions, mtime, ctime, atime,
             is_hidden, attributes}
        """
        if not path.exists():
            return {"path": str(path), "exists": False}

        s = path.stat() if follow_symlinks else path.lstat()
        is_dir = stat.S_ISDIR(s.st_mode)
        is_file = stat.S_ISREG(s.st_mode)
        is_link = path.is_symlink()

        file_type = "directory" if is_dir else "file" if is_file else "other"
        if is_link:
            file_type = "symlink"

        attributes = get_file_attributes_from_stat(s)

        result = {
            "path": str(path),
            "exists": True,
            "type": file_type,
            "size": s.st_size,
            "permissions": oct(s.st_mode & 0o777),
            "mtime": datetime.fromtimestamp(s.st_mtime, tz=timezone.utc).isoformat(),
            "ctime": datetime.fromtimestamp(s.st_ctime, tz=timezone.utc).isoformat(),
            "atime": datetime.fromtimestamp(s.st_atime, tz=timezone.utc).isoformat(),
            "is_hidden": is_hidden(path),
            "is_symlink": is_link,
            "attributes": attributes,
        }

        if is_link:
            try:
                result["symlink_target"] = str(path.resolve())
            except OSError:
                result["symlink_target"] = None

        return result

    async def exists(
        self,
        ctx: RequestContext,
        path: Path,
    ) -> dict[str, Any]:
        """检查文件/目录是否存在"""
        e = path.exists()
        result: dict[str, Any] = {"path": str(path), "exists": e}
        if e:
            result["type"] = "directory" if path.is_dir() else "file"
        return result

    async def list_directory(
        self,
        ctx: RequestContext,
        path: Path,
        pattern: str | None = None,
        recursive: bool = False,
        include_hidden: bool = False,
        max_results: int | None = None,
    ) -> dict[str, Any]:
        """
        列出目录内容

        Args:
            path: 目录绝对路径
            pattern: glob 模式过滤（如 "*.py"）
            recursive: 是否递归子目录
            include_hidden: 是否包含隐藏文件
            max_results: 最大返回条数，None 使用配置默认值

        Returns:
            {path, entries: [{name, type, size, mtime, is_hidden}], total, truncated}
        """
        if not path.exists():
            raise FileNotFoundError(
                f"目录不存在: {path}",
                details={"path": str(path)},
            )
        if not path.is_dir():
            raise InvalidParameterError(
                f"路径不是目录: {path}",
                details={"path": str(path)},
            )

        limit = max_results or self.config.performance.max_search_results
        entries: list[dict[str, Any]] = []
        total = 0

        # 使用缓存
        cache_key = f"{path}:{pattern}:{recursive}:{include_hidden}"
        cached = self.cache.get("directory", cache_key)
        if cached is not None:
            return cached

        try:
            iterator = path.rglob(pattern or "*") if recursive else path.glob(pattern or "*")

            for item in iterator:
                # 隐藏文件过滤
                if not include_hidden and is_hidden(item):
                    continue

                total += 1
                if len(entries) >= limit:
                    continue  # 继续计数但不再收集

                try:
                    s = item.stat()
                except OSError:
                    continue

                entries.append({
                    "name": str(item.relative_to(path)),
                    "type": "directory" if item.is_dir() else "file",
                    "size": s.st_size if item.is_file() else None,
                    "mtime": datetime.fromtimestamp(
                        s.st_mtime, tz=timezone.utc
                    ).isoformat(),
                    "is_hidden": is_hidden(item),
                })
        except PermissionError:
            raise PermissionDeniedError(
                f"无权限读取目录: {path}",
                details={"path": str(path)},
            )

        truncated = total > limit
        if truncated:
            ctx.warn(
                WARNING_PARTIAL_RESULT,
                f"结果已截断: 共 {total} 项，仅返回 {limit} 项",
                total=total,
                returned=limit,
            )

        result = {
            "path": str(path),
            "entries": entries,
            "total": total,
            "truncated": truncated,
        }

        # 缓存结果
        self.cache.set("directory", cache_key, result)
        return result

    # ═══════════════════════════════════════════════════
    #  写入类
    # ═══════════════════════════════════════════════════

    async def create_file(
        self,
        ctx: RequestContext,
        path: Path,
        content: str = "",
        encoding: str = "utf-8",
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """
        创建文件

        Args:
            path: 目标路径
            content: 文件内容
            encoding: 写入编码
            overwrite: 已存在时是否覆写
        """
        if path.exists() and not overwrite:
            raise ConcurrentModificationError(
                f"文件已存在: {path}",
                details={"path": str(path)},
                suggestion="设置 overwrite=true 以覆写",
            )

        # 确保父目录存在
        path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(path, mode="w", encoding=encoding) as f:
            await f.write(content)

        size = path.stat().st_size

        # 失效相关缓存
        self._invalidate_path_cache(path)

        return {
            "path": str(path),
            "size": size,
            "encoding": encoding,
            "created": True,
        }

    async def write_file(
        self,
        ctx: RequestContext,
        path: Path,
        content: str,
        encoding: str = "utf-8",
    ) -> dict[str, Any]:
        """
        覆写文件（文件必须存在）

        Args:
            path: 目标路径
            content: 新内容
            encoding: 写入编码
        """
        if not path.exists():
            raise FileNotFoundError(
                f"文件不存在: {path}",
                details={"path": str(path)},
                suggestion="使用 create_file 创建新文件",
            )

        async with aiofiles.open(path, mode="w", encoding=encoding) as f:
            await f.write(content)

        size = path.stat().st_size
        self._invalidate_path_cache(path)

        return {
            "path": str(path),
            "size": size,
            "encoding": encoding,
        }

    async def create_directory(
        self,
        ctx: RequestContext,
        path: Path,
        recursive: bool = True,
    ) -> dict[str, Any]:
        """创建目录"""
        path.mkdir(parents=recursive, exist_ok=True)
        self._invalidate_path_cache(path.parent)
        return {"path": str(path), "created": True}

    # ═══════════════════════════════════════════════════
    #  修改类
    # ═══════════════════════════════════════════════════

    async def replace_range(
        self,
        ctx: RequestContext,
        path: Path,
        start_line: int,
        end_line: int,
        new_text: str,
        encoding: str = "utf-8",
    ) -> dict[str, Any]:
        """
        替换文件中指定行范围的文本

        Args:
            path: 文件路径
            start_line: 起始行号（1-based，含）
            end_line: 结束行号（1-based，含）
            new_text: 替换后的文本
            encoding: 文件编码
        """
        content = await self._read_text(path, encoding)
        lines = content.splitlines(keepends=True)
        total = len(lines)

        if start_line < 1 or end_line < start_line or start_line > total:
            raise InvalidParameterError(
                f"行号范围无效: [{start_line}, {end_line}]，文件共 {total} 行",
                details={"start_line": start_line, "end_line": end_line, "total_lines": total},
            )

        # 替换
        end_line = min(end_line, total)
        replaced_text = "".join(lines[start_line - 1 : end_line])
        new_lines = new_text.splitlines(keepends=True)
        # 确保 new_text 以换行结尾（如果原文最后一行有换行）
        if new_text and not new_text.endswith("\n") and end_line < total:
            new_lines.append("\n" if lines[end_line - 1].endswith("\n") else "")

        lines[start_line - 1 : end_line] = new_lines
        result_content = "".join(lines)

        async with aiofiles.open(path, mode="w", encoding=encoding) as f:
            await f.write(result_content)

        self._invalidate_path_cache(path)

        return {
            "path": str(path),
            "replaced_lines": [start_line, end_line],
            "old_text": replaced_text,
            "new_text": new_text,
            "total_lines": len(result_content.splitlines()),
        }

    async def insert_text(
        self,
        ctx: RequestContext,
        path: Path,
        line: int,
        text: str,
        encoding: str = "utf-8",
    ) -> dict[str, Any]:
        """
        在指定行之前插入文本

        Args:
            path: 文件路径
            line: 行号（1-based），在此行之前插入
            text: 要插入的文本
            encoding: 文件编码
        """
        content = await self._read_text(path, encoding)
        lines = content.splitlines(keepends=True)
        total = len(lines)

        if line < 1 or line > total + 1:
            raise InvalidParameterError(
                f"行号无效: {line}，有效范围 [1, {total + 1}]",
                details={"line": line, "total_lines": total},
            )

        insert_lines = text.splitlines(keepends=True)
        # 确保插入文本以换行结尾
        if text and not text.endswith("\n"):
            insert_lines[-1] += "\n"

        lines[line - 1 : line - 1] = insert_lines
        result_content = "".join(lines)

        async with aiofiles.open(path, mode="w", encoding=encoding) as f:
            await f.write(result_content)

        self._invalidate_path_cache(path)

        return {
            "path": str(path),
            "inserted_at": line,
            "inserted_lines": len(insert_lines),
            "total_lines": len(result_content.splitlines()),
        }

    async def delete_range(
        self,
        ctx: RequestContext,
        path: Path,
        start_line: int,
        end_line: int,
        encoding: str = "utf-8",
    ) -> dict[str, Any]:
        """
        删除文件中指定行范围

        Args:
            path: 文件路径
            start_line: 起始行号（1-based，含）
            end_line: 结束行号（1-based，含）
        """
        content = await self._read_text(path, encoding)
        lines = content.splitlines(keepends=True)
        total = len(lines)

        if start_line < 1 or end_line < start_line or start_line > total:
            raise InvalidParameterError(
                f"行号范围无效: [{start_line}, {end_line}]，文件共 {total} 行",
                details={"start_line": start_line, "end_line": end_line, "total_lines": total},
            )

        end_line = min(end_line, total)
        deleted_text = "".join(lines[start_line - 1 : end_line])
        del lines[start_line - 1 : end_line]
        result_content = "".join(lines)

        async with aiofiles.open(path, mode="w", encoding=encoding) as f:
            await f.write(result_content)

        self._invalidate_path_cache(path)

        return {
            "path": str(path),
            "deleted_lines": [start_line, end_line],
            "deleted_text": deleted_text,
            "total_lines": len(result_content.splitlines()),
        }

    async def apply_patch(
        self,
        ctx: RequestContext,
        path: Path,
        patch: str,
        dry_run: bool = False,
        encoding: str = "utf-8",
    ) -> dict[str, Any]:
        """
        应用 unified diff 补丁

        Args:
            path: 文件路径
            patch: unified diff 格式的补丁文本
            dry_run: True 只检查不实际修改
            encoding: 文件编码

        Returns:
            {path, applied, hunks, dry_run}
        """
        content = await self._read_text(path, encoding)
        original_lines = content.splitlines(keepends=True)

        # 解析 patch，提取 hunk
        hunks = self._parse_unified_diff(patch)
        if not hunks:
            raise PatchApplyError(
                "无法解析补丁: 未找到有效的 hunk",
                details={"patch_preview": patch[:200]},
            )

        # 应用 hunks（从后向前，避免行号偏移）
        result_lines = list(original_lines)
        applied_count = 0

        for hunk in reversed(hunks):
            try:
                result_lines = self._apply_hunk(result_lines, hunk)
                applied_count += 1
            except PatchApplyError:
                raise

        if not dry_run:
            result_content = "".join(result_lines)
            async with aiofiles.open(path, mode="w", encoding=encoding) as f:
                await f.write(result_content)
            self._invalidate_path_cache(path)

        return {
            "path": str(path),
            "applied": applied_count,
            "hunks": len(hunks),
            "dry_run": dry_run,
        }

    # ═══════════════════════════════════════════════════
    #  移动/复制/删除
    # ═══════════════════════════════════════════════════

    async def move_file(
        self,
        ctx: RequestContext,
        source: Path,
        dest: Path,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """移动/重命名文件"""
        if not source.exists():
            raise FileNotFoundError(
                f"源文件不存在: {source}",
                details={"source": str(source)},
            )
        if not source.is_file():
            raise InvalidParameterError(
                f"源路径不是文件: {source}",
                details={"source": str(source)},
            )
        if dest.exists() and not overwrite:
            raise ConcurrentModificationError(
                f"目标文件已存在: {dest}",
                details={"dest": str(dest)},
                suggestion="设置 overwrite=true",
            )

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(dest))

        self._invalidate_path_cache(source)
        self._invalidate_path_cache(dest)

        return {"source": str(source), "dest": str(dest)}

    async def copy_file(
        self,
        ctx: RequestContext,
        source: Path,
        dest: Path,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """复制文件"""
        if not source.exists():
            raise FileNotFoundError(
                f"源文件不存在: {source}",
                details={"source": str(source)},
            )
        if dest.exists() and not overwrite:
            raise ConcurrentModificationError(
                f"目标文件已存在: {dest}",
                details={"dest": str(dest)},
                suggestion="设置 overwrite=true",
            )

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(source), str(dest))

        self._invalidate_path_cache(dest)

        return {
            "source": str(source),
            "dest": str(dest),
            "size": dest.stat().st_size,
        }

    async def delete_file(
        self,
        ctx: RequestContext,
        path: Path,
    ) -> dict[str, Any]:
        """删除文件"""
        if not path.exists():
            raise FileNotFoundError(
                f"文件不存在: {path}",
                details={"path": str(path)},
            )
        if not path.is_file():
            raise InvalidParameterError(
                f"路径不是文件: {path}",
                details={"path": str(path)},
                suggestion="使用 delete_directory 删除目录",
            )

        path.unlink()
        self._invalidate_path_cache(path)

        return {"path": str(path), "deleted": True}

    async def move_directory(
        self,
        ctx: RequestContext,
        source: Path,
        dest: Path,
    ) -> dict[str, Any]:
        """移动/重命名目录"""
        if not source.exists():
            raise FileNotFoundError(
                f"源目录不存在: {source}",
                details={"source": str(source)},
            )
        if not source.is_dir():
            raise InvalidParameterError(
                f"源路径不是目录: {source}",
                details={"source": str(source)},
            )
        if dest.exists():
            raise ConcurrentModificationError(
                f"目标路径已存在: {dest}",
                details={"dest": str(dest)},
            )

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(dest))

        self._invalidate_path_cache(source)
        self._invalidate_path_cache(dest)

        return {"source": str(source), "dest": str(dest)}

    async def delete_directory(
        self,
        ctx: RequestContext,
        path: Path,
        recursive: bool = False,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        删除目录

        Args:
            path: 目录路径
            recursive: 是否递归删除（含子目录/文件）
            force: 是否忽略只读文件（设置可写后删除）
        """
        if not path.exists():
            raise FileNotFoundError(
                f"目录不存在: {path}",
                details={"path": str(path)},
            )
        if not path.is_dir():
            raise InvalidParameterError(
                f"路径不是目录: {path}",
                details={"path": str(path)},
            )

        if recursive:
            if force:
                # 清除只读属性后删除
                def _on_error(func: Any, fpath: str, exc_info: Any) -> None:
                    os.chmod(fpath, stat.S_IWRITE)
                    func(fpath)

                shutil.rmtree(str(path), onerror=_on_error)
            else:
                shutil.rmtree(str(path))
        else:
            try:
                path.rmdir()
            except OSError as e:
                raise InvalidParameterError(
                    f"目录非空，需设置 recursive=true: {path}",
                    details={"path": str(path)},
                    cause=e,
                )

        self._invalidate_path_cache(path)

        return {"path": str(path), "deleted": True}

    # ═══════════════════════════════════════════════════
    #  内部方法
    # ═══════════════════════════════════════════════════

    async def _read_text(self, path: Path, encoding: str = "utf-8") -> str:
        """读取文件文本内容"""
        if not path.exists():
            raise FileNotFoundError(
                f"文件不存在: {path}",
                details={"path": str(path)},
            )
        try:
            async with aiofiles.open(path, mode="r", encoding=encoding) as f:
                return await f.read()
        except UnicodeDecodeError as e:
            raise EncodingError(
                f"文件解码失败 (encoding={encoding}): {e}",
                details={"path": str(path), "encoding": encoding},
                cause=e,
            )

    def _invalidate_path_cache(self, path: Path) -> None:
        """使与路径相关的缓存失效"""
        self.cache.invalidate("metadata", str(path))
        # 父目录的 directory 缓存也需要失效
        self.cache.invalidate_prefix("directory", str(path.parent))

    @staticmethod
    def _parse_unified_diff(patch: str) -> list[dict[str, Any]]:
        """
        解析 unified diff 格式补丁

        Returns:
            [{old_start, old_count, new_start, new_count, lines}]
        """
        import re

        hunks: list[dict[str, Any]] = []
        hunk_header = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

        current_hunk: dict[str, Any] | None = None

        for line in patch.splitlines(keepends=True):
            m = hunk_header.match(line)
            if m:
                if current_hunk is not None:
                    hunks.append(current_hunk)
                current_hunk = {
                    "old_start": int(m.group(1)),
                    "old_count": int(m.group(2) or 1),
                    "new_start": int(m.group(3)),
                    "new_count": int(m.group(4) or 1),
                    "lines": [],
                }
            elif current_hunk is not None:
                if line.startswith(("+", "-", " ")):
                    current_hunk["lines"].append(line)

        if current_hunk is not None:
            hunks.append(current_hunk)

        return hunks

    @staticmethod
    def _apply_hunk(
        lines: list[str], hunk: dict[str, Any]
    ) -> list[str]:
        """
        将单个 hunk 应用到行列表

        逐行处理 unified diff 的三种前缀:
        - " " 上下文行: 验证匹配，保留
        - "-" 删除行: 验证匹配，移除
        - "+" 添加行: 插入新内容

        Raises:
            PatchApplyError: 上下文不匹配时
        """
        old_start = hunk["old_start"] - 1  # 0-based
        old_idx = old_start
        new_lines: list[str] = []
        # 保留 hunk 之前的所有行
        new_lines.extend(lines[:old_start])

        for patch_line in hunk["lines"]:
            prefix = patch_line[0]
            content = patch_line[1:]

            if prefix == " ":
                # 上下文行: 验证匹配，保留
                if old_idx >= len(lines):
                    raise PatchApplyError(
                        f"补丁上下文不匹配: 行 {old_idx + 1} 超出文件范围",
                        details={"expected_line": old_idx + 1, "total_lines": len(lines)},
                    )
                if lines[old_idx].rstrip("\r\n") != content.rstrip("\r\n"):
                    raise PatchApplyError(
                        f"补丁上下文不匹配: 行 {old_idx + 1}",
                        details={
                            "expected": content.rstrip(),
                            "actual": lines[old_idx].rstrip(),
                        },
                    )
                new_lines.append(lines[old_idx])
                old_idx += 1

            elif prefix == "-":
                # 删除行: 验证匹配，跳过（不加入 new_lines）
                if old_idx >= len(lines):
                    raise PatchApplyError(
                        f"补丁删除行不匹配: 行 {old_idx + 1} 超出文件范围",
                        details={"expected_line": old_idx + 1, "total_lines": len(lines)},
                    )
                if lines[old_idx].rstrip("\r\n") != content.rstrip("\r\n"):
                    raise PatchApplyError(
                        f"补丁删除行不匹配: 行 {old_idx + 1}",
                        details={
                            "expected": content.rstrip(),
                            "actual": lines[old_idx].rstrip(),
                        },
                    )
                old_idx += 1  # 跳过此行

            elif prefix == "+":
                # 添加行: 插入新内容
                new_lines.append(content)

        # 保留 hunk 之后的所有行
        new_lines.extend(lines[old_idx:])
        return new_lines
