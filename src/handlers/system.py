"""
Layer 4: Handlers — 系统管理

提供服务级别的工具方法:
  ping           → 健康检查
  get_version    → 版本信息
  get_methods    → 已注册方法列表
  get_config     → 当前配置（脱敏）
  set_workspace  → 动态切换工作区
  get_stats      → 缓存/任务统计
  clear_cache    → 清空缓存

依赖:
- Layer 1: core (MCPConfig, CacheManager, ConfigHolder)
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..core.cache import CacheManager
from ..core.config import ConfigHolder, MCPConfig
from ..core.errors import InvalidParameterError
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
        self._registered_methods: list[str] = []

    def set_registered_methods(self, methods: list[str]) -> None:
        """由 Protocol 层调用，注入已注册的方法列表"""
        self._registered_methods = sorted(methods)

    # ═══════════════════════════════════════════════════
    #  方法实现
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

    async def get_version(
        self,
        ctx: RequestContext,
    ) -> dict[str, Any]:
        """版本信息"""
        return {
            "version": __version__,
            "python": _python_version(),
        }

    async def get_methods(
        self,
        ctx: RequestContext,
    ) -> dict[str, Any]:
        """列出所有已注册的方法"""
        return {
            "methods": self._registered_methods,
            "total": len(self._registered_methods),
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
