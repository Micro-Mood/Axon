"""
Layer 1: Core — 配置管理

基于 Pydantic v2，支持:
- 文件加载 (config.json)
- 环境变量覆盖 (MCP_*)
- 运行时动态修改
- 热重载 + 监听器通知
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field

from .errors import ConfigLoadError


# ═══════════════════════════════════════════════════════
#  子配置模型
# ═══════════════════════════════════════════════════════

class WorkspaceConfig(BaseModel):
    """工作区配置"""
    root_path: str = "."
    allowed_extensions: list[str] = Field(default_factory=list)
    max_depth: int = 20

    # 计算属性: 解析后的绝对路径
    @property
    def root(self) -> Path:
        return Path(self.root_path).resolve()


class SecurityConfig(BaseModel):
    """安全规则 — 默认值由 platform 层提供，这里只定义结构"""
    blocked_paths: list[str] = Field(default_factory=list)
    blocked_commands: list[str] = Field(default_factory=list)
    allowed_shells: list[str] = Field(default_factory=list)
    max_file_size_mb: int = 100
    follow_symlinks: bool = False


class PerformanceConfig(BaseModel):
    """性能限制"""
    max_concurrent_tasks: int = 10
    cache_ttl: int = 60
    max_search_results: int = 1000
    default_timeout_ms: int = 30000
    max_output_buffer_mb: int = 10


class LoggingConfig(BaseModel):
    """日志配置"""
    level: str = "INFO"
    audit_enabled: bool = True
    log_file: str | None = None


class ServerConfig(BaseModel):
    """服务器配置"""
    host: str = "127.0.0.1"
    port: int = 9100
    transport: str = "tcp"  # "tcp" | "stdio"


# ═══════════════════════════════════════════════════════
#  顶层配置
# ═══════════════════════════════════════════════════════

class MCPConfig(BaseModel):
    """MCP 全局配置"""
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)


# ═══════════════════════════════════════════════════════
#  配置加载器
# ═══════════════════════════════════════════════════════

# 环境变量前缀
_ENV_PREFIX = "MCP_"

# 环境变量 → 配置路径映射
_ENV_MAP: dict[str, tuple[str, str, type]] = {
    # 环境变量名: (子配置名, 字段名, 类型)
    "MCP_WORKSPACE_ROOT": ("workspace", "root_path", str),
    "MCP_MAX_DEPTH": ("workspace", "max_depth", int),
    "MCP_MAX_FILE_SIZE_MB": ("security", "max_file_size_mb", int),
    "MCP_FOLLOW_SYMLINKS": ("security", "follow_symlinks", bool),
    "MCP_MAX_CONCURRENT_TASKS": ("performance", "max_concurrent_tasks", int),
    "MCP_CACHE_TTL": ("performance", "cache_ttl", int),
    "MCP_DEFAULT_TIMEOUT_MS": ("performance", "default_timeout_ms", int),
    "MCP_LOG_LEVEL": ("logging", "level", str),
    "MCP_AUDIT_ENABLED": ("logging", "audit_enabled", bool),
    "MCP_LOG_FILE": ("logging", "log_file", str),
    "MCP_HOST": ("server", "host", str),
    "MCP_PORT": ("server", "port", int),
    "MCP_TRANSPORT": ("server", "transport", str),
}


def _parse_env_value(value: str, target_type: type) -> Any:
    """将环境变量字符串转为目标类型"""
    if target_type is bool:
        return value.lower() in ("true", "1", "yes")
    if target_type is int:
        return int(value)
    return value


def load_config(config_path: str | Path | None = None) -> MCPConfig:
    """
    加载配置

    优先级（高→低）:
    1. 环境变量 MCP_*
    2. 配置文件 config.json
    3. 代码默认值

    Args:
        config_path: 配置文件路径，None 则只用默认值+环境变量
    """
    # Step 1: 从文件加载基础配置
    file_data: dict = {}
    if config_path is not None:
        p = Path(config_path)
        if p.exists():
            try:
                file_data = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                raise ConfigLoadError(
                    f"配置文件加载失败: {p}",
                    cause=e,
                    suggestion="请检查 JSON 格式是否正确",
                )

    # Step 2: 创建 config（文件数据 + 默认值）
    config = MCPConfig.model_validate(file_data)

    # Step 3: 环境变量覆盖
    for env_key, (section, field_name, field_type) in _ENV_MAP.items():
        env_val = os.environ.get(env_key)
        if env_val is not None:
            sub_config = getattr(config, section)
            setattr(sub_config, field_name, _parse_env_value(env_val, field_type))

    return config


# ═══════════════════════════════════════════════════════
#  配置持有者（支持热重载）
# ═══════════════════════════════════════════════════════

class ConfigHolder:
    """
    配置持有者，支持热重载与监听

    用法:
        holder = ConfigHolder(load_config("config.json"))
        holder.on_reload(lambda c: print("reloaded"))
        holder.reload("config.json")
    """

    def __init__(self, config: MCPConfig):
        self._config = config
        self._listeners: list[Callable[[MCPConfig], None]] = []

    @property
    def config(self) -> MCPConfig:
        return self._config

    def on_reload(self, listener: Callable[[MCPConfig], None]) -> None:
        """注册重载监听器"""
        self._listeners.append(listener)

    def reload(self, config_path: str | Path | None = None) -> MCPConfig:
        """重新加载配置并通知监听者"""
        self._config = load_config(config_path)
        for listener in self._listeners:
            listener(self._config)
        return self._config

    def update(self, **kwargs: Any) -> None:
        """
        运行时动态修改

        用法:
            holder.update(workspace={"root_path": "/new/path"})
        """
        data = self._config.model_dump()
        for key, value in kwargs.items():
            if key in data and isinstance(value, dict):
                data[key].update(value)
            else:
                data[key] = value
        self._config = MCPConfig.model_validate(data)
        for listener in self._listeners:
            listener(self._config)
