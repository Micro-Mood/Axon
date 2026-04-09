"""
Layer 5: Middleware — 安全中间件

职责:
- 自动检测请求参数中的路径和命令
- 对路径参数调用 SecurityChecker.validate_path()
- 对命令参数调用 SecurityChecker.validate_command()
- 对环境变量参数调用 SecurityChecker.validate_env()
- 对 cwd 参数调用 SecurityChecker.validate_cwd()
- 校验后的绝对路径写入 ctx.validated_paths
- 写操作自动检查写权限

handler 不需要手动调用安全检查 — 全部由本中间件自动完成。

依赖:
- Layer 1: core (SecurityChecker, MCPConfig)
- Layer 4: handlers/base (RequestContext)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..core.config import MCPConfig
from ..core.security import SecurityChecker
from ..handlers.base import RequestContext
from .chain import NextFunc

logger = logging.getLogger(__name__)


# ── 参数分类 ──

# 需要做路径校验的参数名
# 注意: set_workspace 的 root_path 不在此处 — 它切换 workspace，不受当前 workspace 约束
_PATH_PARAMS = frozenset({"path", "source", "dest", "root"})

# 需要做命令校验的参数名
_COMMAND_PARAMS = frozenset({"command"})

# 需要做环境变量校验的参数名
_ENV_PARAMS = frozenset({"env"})

# 需要做工作目录校验的参数名
_CWD_PARAMS = frozenset({"cwd"})

# 写操作方法名 — 需要额外检查写权限
_WRITE_METHODS = frozenset({
    "create_file",
    "write_file",
    "replace_range",
    "insert_text",
    "delete_range",
    "apply_patch",
    "move_file",
    "copy_file",
    "delete_file",
    "create_directory",
    "move_directory",
    "delete_directory",
})

# 写操作中的 "目标路径" 参数名（需要检查写权限的）
_WRITE_TARGET_PARAMS = frozenset({"path", "dest"})

# 源路径参数名（写操作中用于读的）
_SOURCE_PARAMS = frozenset({"source"})


class SecurityMiddleware:
    """
    自动安全校验中间件

    根据请求参数名自动决定校验类型:
    - path/source/destination/dest → validate_path()
    - command → validate_command()
    - env → validate_env()
    - cwd → validate_cwd()

    写操作（create_file, write_file 等）额外检查目标路径的写权限。

    校验后的绝对路径写入 ctx.validated_paths:
        ctx.validated_paths["path"] = Path("/abs/path/to/file")

    任何校验失败都会抛对应的 MCPError（不调用 next）。
    """

    def __init__(self, config: MCPConfig, security: SecurityChecker) -> None:
        self._config = config
        self._security = security

    async def __call__(
        self, ctx: RequestContext, next_handler: NextFunc
    ) -> dict[str, Any]:
        workspace = self._config.workspace.root

        # ── 路径校验 ──
        for param_name in _PATH_PARAMS:
            raw_value = ctx.params.get(param_name)
            if raw_value is None:
                continue

            # validate_path: 解析 + workspace 边界 + blocked_paths + symlink
            validated = self._security.validate_path(raw_value, workspace=workspace)

            # 写入 validated_paths 供 handler 使用
            ctx.validated_paths[param_name] = validated

            # 替换原始参数为绝对路径字符串
            ctx.params[param_name] = str(validated)

            logger.debug(
                "路径校验通过: %s=%s → %s",
                param_name,
                raw_value,
                validated,
            )

        # ── 写权限检查 ──
        if ctx.method in _WRITE_METHODS:
            # 目标路径需要写权限
            for param_name in _WRITE_TARGET_PARAMS:
                validated_path = ctx.validated_paths.get(param_name)
                if validated_path is not None:
                    self._security.check_write_permission(validated_path)

            # 源路径需要读权限
            for param_name in _SOURCE_PARAMS:
                validated_path = ctx.validated_paths.get(param_name)
                if validated_path is not None:
                    self._security.check_read_permission(validated_path)

        # ── 命令校验 ──
        for param_name in _COMMAND_PARAMS:
            command = ctx.params.get(param_name)
            if command is not None:
                self._security.validate_command(command)
                logger.debug("命令校验通过: %s", command)

        # ── 环境变量校验 ──
        for param_name in _ENV_PARAMS:
            env = ctx.params.get(param_name)
            if env is not None and isinstance(env, dict):
                self._security.validate_env(env)

        # ── 工作目录校验 ──
        for param_name in _CWD_PARAMS:
            cwd = ctx.params.get(param_name)
            if cwd is not None:
                validated_cwd = self._security.validate_cwd(cwd, workspace=workspace)
                ctx.validated_paths[param_name] = validated_cwd
                ctx.params[param_name] = str(validated_cwd)

        # 全部校验通过 → 继续链条
        return await next_handler(ctx)
