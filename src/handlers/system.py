"""
Layer 4: Handlers — 系统管理

AI 工具:
  get_system_info  → 系统环境信息（OS、架构、Python、Shell、工作区）

协议层方法（不注入 AI，客户端直接调用）:
  ping           → 健康检查
  get_config     → 当前配置（脱敏）
  set_workspace  → 动态切换工作区
  get_stats      → 缓存/任务统计
  clear_cache    → 清空缓存
  list_tools     → 完整工具 schema（带分类和参数定义）

依赖:
- Layer 1: core (MCPConfig, CacheManager, ConfigHolder)
"""

from __future__ import annotations

import os
import platform
import shutil
import time
from pathlib import Path
from typing import Any

from ..core.cache import CacheManager
from ..core.config import ConfigHolder, MCPConfig
from ..core.errors import BlockedPathError, InvalidParameterError
from .base import BaseHandler, RequestContext

# 从顶层 __init__.py 获取版本号
try:
    from .. import __version__
except ImportError:
    __version__ = "unknown"

# 服务启动时间
_START_TIME = time.monotonic()


class SystemHandler(BaseHandler):
    """
    系统管理 handler

    额外依赖: ConfigHolder（用于动态修改配置和获取注册方法列表）
    """

    def __init__(
        self,
        config: MCPConfig,
        cache: CacheManager,
        config_holder: ConfigHolder,
    ):
        super().__init__(config, cache)
        self._config_holder = config_holder
        self._tools: dict | None = None

    def set_tools(self, tools: dict) -> None:
        """由 Protocol 层调用，注入工具定义（用于 list_tools）"""
        self._tools = tools

    # ═══════════════════════════════════════════════════
    #  AI 工具方法
    # ═══════════════════════════════════════════════════

    async def get_system_info(
        self,
        ctx: RequestContext,
    ) -> dict[str, Any]:
        """获取系统环境信息"""
        return {
            "os": platform.system().lower(),
            "arch": platform.machine(),
            "python": _python_version(),
            "shell": _detect_shell(),
            "workspace": str(self.workspace),
            "axon_version": __version__,
        }

    # ═══════════════════════════════════════════════════
    #  协议层方法（客户端直接调用，不注入 AI）
    # ═══════════════════════════════════════════════════

    async def ping(
        self,
        ctx: RequestContext,
    ) -> dict[str, Any]:
        """健康检查"""
        uptime_s = time.monotonic() - _START_TIME
        return {
            "status": "ok",
            "uptime_seconds": round(uptime_s, 1),
        }

    async def list_tools(
        self,
        ctx: RequestContext,
    ) -> dict[str, Any]:
        """
        返回完整的工具 schema（带分类和参数定义）

        客户端调用此方法获取工具列表，构造 AI function calling schema。
        """
        if not self._tools:
            return {"tools": {}, "total": 0}

        grouped: dict[str, list[dict[str, Any]]] = {}
        for t in self._tools.values():
            group = t.group or "other"
            tool_info: dict[str, Any] = {
                "name": t.name,
                "description": t.description,
                "params": [
                    {
                        "name": p.name,
                        "type": p.type,
                        "required": p.required,
                        **({"default": p.default} if not p.required and p.default is not None else {}),
                        **({"description": ""} if False else {}),
                    }
                    for p in t.params
                ],
                "is_write": t.is_write,
            }
            grouped.setdefault(group, []).append(tool_info)

        return {
            "tools": grouped,
            "total": len(self._tools),
        }

    async def get_config(
        self,
        ctx: RequestContext,
    ) -> dict[str, Any]:
        """
        获取当前配置

        注意: 脱敏输出，不暴露完整安全规则
        """
        cfg = self.config
        return {
            "workspace": {
                "root_path": cfg.workspace.root_path,
                "max_depth": cfg.workspace.max_depth,
            },
            "performance": cfg.performance.model_dump(),
            "logging": {
                "level": cfg.logging.level,
                "audit_enabled": cfg.logging.audit_enabled,
            },
            "server": cfg.server.model_dump(),
        }

    async def set_workspace(
        self,
        ctx: RequestContext,
        root_path: str,
    ) -> dict[str, Any]:
        """
        动态切换工作区

        Args:
            root_path: 新的工作区根路径
        """
        p = Path(root_path).resolve()
        if not p.exists():
            raise InvalidParameterError(
                f"工作区路径不存在: {root_path}",
                details={"root_path": root_path},
            )
        if not p.is_dir():
            raise InvalidParameterError(
                f"工作区路径不是目录: {root_path}",
                details={"root_path": root_path},
            )

        # 检查 blocked_paths — 禁止切换到系统敏感目录
        import os
        resolved_str = str(p)
        for blocked in self.config.security.blocked_paths:
            blocked_resolved = str(Path(blocked).resolve())
            if resolved_str == blocked_resolved or resolved_str.startswith(
                blocked_resolved + os.sep
            ):
                raise BlockedPathError(
                    f"工作区路径被禁止: {root_path}",
                    details={"root_path": resolved_str, "blocked_by": blocked},
                )

        self._config_holder.update(workspace={"root_path": str(p)})

        # 清空目录和搜索缓存（旧工作区的缓存无效了）
        self.cache.clear("directory")
        self.cache.clear("search")
        self.cache.clear("metadata")

        return {
            "root_path": str(p),
            "message": f"工作区已切换到: {p}",
        }

    async def get_stats(
        self,
        ctx: RequestContext,
    ) -> dict[str, Any]:
        """获取缓存统计"""
        uptime_s = time.monotonic() - _START_TIME
        return {
            "uptime_seconds": round(uptime_s, 1),
            "cache": self.cache.stats(),
        }

    async def clear_cache(
        self,
        ctx: RequestContext,
        bucket: str | None = None,
    ) -> dict[str, Any]:
        """
        清空缓存

        Args:
            bucket: 指定桶名（metadata/directory/search/task），None 清空全部
        """
        self.cache.clear(bucket)
        return {
            "cleared": bucket or "all",
            "message": f"缓存已清空: {bucket or '全部'}",
        }


# ═══════════════════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════════════════

def _python_version() -> str:
    import sys
    v = sys.version_info
    return f"{v.major}.{v.minor}.{v.micro}"


def _detect_shell() -> str:
    """检测当前系统默认 shell"""
    if platform.system() == "Windows":
        comspec = os.environ.get("COMSPEC", "")
        if "powershell" in comspec.lower() or shutil.which("pwsh"):
            return "powershell"
        return "cmd"
    shell = os.environ.get("SHELL", "")
    if shell:
        return Path(shell).name
    return "sh"
