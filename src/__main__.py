"""
Axon MCP Server 入口

用法:
    # TCP 模式（默认）
    python -m src

    # Stdio 模式
    python -m src --transport stdio

    # 指定配置文件
    python -m src --config config.json

    # 指定端口
    python -m src --port 9200

    # 指定工作区
    python -m src --workspace /path/to/workspace
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .core.config import MCPConfig, load_config
from .protocol import MCPServer, create_transport


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="axon",
        description="Axon MCP Server — 跨平台文件/命令操作服务",
    )
    parser.add_argument(
        "--config", "-c",
        help="配置文件路径 (JSON)",
        default=None,
    )
    parser.add_argument(
        "--transport", "-t",
        choices=["tcp", "stdio"],
        default="tcp",
        help="传输模式 (默认: tcp)",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="TCP 监听地址 (默认: 127.0.0.1)",
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=None,
        help="TCP 监听端口 (默认: 9100)",
    )
    parser.add_argument(
        "--workspace", "-w",
        default=None,
        help="工作区根路径",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="日志级别",
    )
    return parser.parse_args()


def setup_logging(level: str = "INFO") -> None:
    """配置日志"""
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,  # 日志写 stderr，stdout 留给 stdio 传输
    )


def main() -> None:
    args = parse_args()

    # 加载配置
    if args.config:
        config = load_config(args.config)
    else:
        config = MCPConfig()

    # 命令行覆盖
    if args.workspace:
        config.workspace.root_path = args.workspace
    if args.host:
        config.server.host = args.host
    if args.port:
        config.server.port = args.port
    if args.transport:
        config.server.transport = args.transport
    if args.log_level:
        config.logging.level = args.log_level

    # 日志
    setup_logging(config.logging.level)

    # 创建服务
    server = MCPServer(config)
    transport = create_transport(
        server,
        transport_type=config.server.transport,
    )

    # 启动
    try:
        asyncio.run(transport.start())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
