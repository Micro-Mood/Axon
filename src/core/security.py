"""
Layer 1: Core — 安全校验器

纯校验逻辑，无状态。
不包含文件操作、文件锁、校验和计算（那些归 handler / platform）。

依赖:
- config.SecurityConfig (结构)
- errors (异常类型)
- 注意: 不依赖 platform 层 — platform 相关校验由 middleware 或上层协调
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from .config import SecurityConfig
from .errors import (
    BlockedCommandError,
    BlockedPathError,
    PathOutsideWorkspaceError,
    PermissionDeniedError,
    SizeLimitExceededError,
    SymlinkError,
)


class SecurityChecker:
    """
    无状态安全校验器

    所有方法都是纯校验: 输入 → 通过 / 抛异常
    不做任何 I/O 操作
    """

    def __init__(self, config: SecurityConfig):
        self._config = config
        # 预编译 blocked_commands 的正则匹配
        self._blocked_cmd_patterns: list[re.Pattern] = [
            re.compile(re.escape(cmd), re.IGNORECASE)
            for cmd in config.blocked_commands
        ]

    # ── 路径校验 ──

    def validate_path(self, path: str, workspace: Path) -> Path:
        """
        校验路径安全性，返回解析后的绝对路径

        检查顺序:
        1. 解析为绝对路径
        2. 检查是否在 workspace 内
        3. 检查是否在 blocked_paths 中
        4. 检查符号链接

        Args:
            path: 原始路径（相对或绝对）
            workspace: 工作区根路径（已 resolve）

        Returns:
            验证通过的绝对路径

        Raises:
            PathOutsideWorkspaceError
            BlockedPathError
            SymlinkError
        """
        # 解析为绝对路径
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = workspace / resolved
        resolved = resolved.resolve()

        # workspace 边界检查
        try:
            resolved.relative_to(workspace)
        except ValueError:
            raise PathOutsideWorkspaceError(
                f"路径不在工作区内: {path}",
                details={"path": str(resolved), "workspace": str(workspace)},
            )

        # blocked_paths 检查
        resolved_str = str(resolved)
        for blocked in self._config.blocked_paths:
            blocked_resolved = str(Path(blocked).resolve())
            if resolved_str == blocked_resolved or resolved_str.startswith(
                blocked_resolved + os.sep
            ):
                raise BlockedPathError(
                    f"路径被禁止访问: {path}",
                    details={"path": resolved_str, "blocked_by": blocked},
                )

        # 符号链接检查
        if not self._config.follow_symlinks and Path(path).is_symlink():
            real_target = Path(path).resolve()
            try:
                real_target.relative_to(workspace)
            except ValueError:
                raise SymlinkError(
                    f"符号链接指向工作区外: {path} → {real_target}",
                    details={
                        "symlink": str(path),
                        "target": str(real_target),
                        "workspace": str(workspace),
                    },
                    suggestion="设置 follow_symlinks=true 或将目标移入工作区",
                )

        return resolved

    def check_read_permission(self, path: Path) -> None:
        """检查文件是否可读"""
        if path.exists() and not os.access(path, os.R_OK):
            raise PermissionDeniedError(
                f"无读取权限: {path}",
                details={"path": str(path)},
            )

    def check_write_permission(self, path: Path) -> None:
        """检查文件/目录是否可写"""
        # 文件存在 → 检查文件本身
        if path.exists():
            if not os.access(path, os.W_OK):
                raise PermissionDeniedError(
                    f"无写入权限: {path}",
                    details={"path": str(path)},
                )
        else:
            # 文件不存在 → 检查父目录
            parent = path.parent
            if parent.exists() and not os.access(parent, os.W_OK):
                raise PermissionDeniedError(
                    f"无法在目录中创建文件: {parent}",
                    details={"path": str(path), "parent": str(parent)},
                )

    # ── 命令校验 ──

    def validate_command(self, command: str) -> None:
        """
        校验命令安全性

        Raises:
            BlockedCommandError
        """
        for i, pattern in enumerate(self._blocked_cmd_patterns):
            if pattern.search(command):
                raise BlockedCommandError(
                    f"命令被禁止: {command}",
                    details={
                        "command": command,
                        "blocked_by": self._config.blocked_commands[i],
                    },
                )

    def validate_shell(self, shell: str) -> None:
        """
        校验 shell 是否在允许列表中

        Raises:
            BlockedCommandError
        """
        if self._config.allowed_shells:
            shell_name = Path(shell).name.lower()
            allowed_names = [Path(s).name.lower() for s in self._config.allowed_shells]
            if shell_name not in allowed_names:
                raise BlockedCommandError(
                    f"Shell 不在允许列表中: {shell}",
                    details={
                        "shell": shell,
                        "allowed": self._config.allowed_shells,
                    },
                )

    # ── 文件大小校验 ──

    def check_file_size(self, path: Path) -> None:
        """
        检查文件大小是否超限

        Raises:
            SizeLimitExceededError
        """
        if not path.exists():
            return
        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > self._config.max_file_size_mb:
            raise SizeLimitExceededError(
                f"文件过大: {size_mb:.1f}MB (限制 {self._config.max_file_size_mb}MB)",
                details={
                    "path": str(path),
                    "size_mb": round(size_mb, 2),
                    "limit_mb": self._config.max_file_size_mb,
                },
            )
