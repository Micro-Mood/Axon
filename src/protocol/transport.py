"""
Layer 6: Protocol — 传输层

职责:
- TCP 传输: asyncio TCP server，行分隔 JSON
- Stdio 传输: stdin/stdout，行分隔 JSON
- 连接管理（TCP 多客户端）
- 优雅关闭

协议约定:
- 每条消息 = 一行 JSON + 换行符 '\\n'
- 每行是一个完整的 JSON-RPC 2.0 请求/响应
- 空行忽略

依赖:
- Layer 6: protocol/server (MCPServer)
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import Any

from .server import MCPServer

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
#  TCP Transport
# ═══════════════════════════════════════════════════════

class TCPTransport:
    """
    TCP 传输层

    每个客户端连接独立处理，共享同一个 MCPServer 实例。
    协议: 行分隔 JSON (每行一个 JSON-RPC 请求)。

    用法::

        server = MCPServer(config)
        transport = TCPTransport(server, host="127.0.0.1", port=9100)
        await transport.start()  # 阻塞直到关闭
    """

    def __init__(
        self,
        server: MCPServer,
        host: str = "127.0.0.1",
        port: int = 9100,
    ) -> None:
        self._server = server
        self._host = host
        self._port = port
        self._tcp_server: asyncio.Server | None = None
        self._connections: set[asyncio.Task] = set()
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """启动 TCP 服务器"""
        await self._server.startup()

        self._tcp_server = await asyncio.start_server(
            self._handle_connection,
            self._host,
            self._port,
        )

        addrs = [str(s.getsockname()) for s in self._tcp_server.sockets]
        logger.info("TCP 服务监听: %s", ", ".join(addrs))

        # 注册信号处理
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._signal_handler)
            except NotImplementedError:
                # Windows 不完全支持 add_signal_handler
                pass

        try:
            await self._shutdown_event.wait()
        finally:
            await self.stop()

    async def stop(self) -> None:
        """关闭 TCP 服务器"""
        if self._tcp_server is None:
            return

        logger.info("TCP 服务器关闭中...")

        # 关闭监听
        self._tcp_server.close()
        await self._tcp_server.wait_closed()

        # 取消活跃连接
        for task in self._connections:
            task.cancel()
        if self._connections:
            await asyncio.gather(*self._connections, return_exceptions=True)

        # 关闭 MCPServer
        await self._server.shutdown()

        logger.info("TCP 服务器已关闭")

    def _signal_handler(self) -> None:
        """信号处理"""
        logger.info("收到关闭信号")
        self._shutdown_event.set()

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """处理单个客户端连接"""
        peer = writer.get_extra_info("peername")
        logger.info("客户端连接: %s", peer)

        task = asyncio.current_task()
        if task is not None:
            self._connections.add(task)

        try:
            while True:
                try:
                    line = await reader.readline()
                except ConnectionError:
                    break

                if not line:
                    break  # EOF

                # 解码并去除换行
                try:
                    request_str = line.decode("utf-8").strip()
                except UnicodeDecodeError:
                    request_str = line.decode("utf-8", errors="replace").strip()

                if not request_str:
                    continue  # 空行忽略

                # 处理请求
                response = await self._server.handle_request(request_str)

                if response:  # 通知无响应
                    writer.write((response + "\n").encode("utf-8"))
                    await writer.drain()

        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("连接处理异常: %s", peer)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

            if task is not None:
                self._connections.discard(task)
            logger.info("客户端断开: %s", peer)


# ═══════════════════════════════════════════════════════
#  Stdio Transport
# ═══════════════════════════════════════════════════════

class StdioTransport:
    """
    Stdio 传输层

    从 stdin 读取，写入 stdout。
    适用于被父进程启动的子进程模式 (MCP SDK 标准用法)。

    协议: 行分隔 JSON，同 TCP。

    用法::

        server = MCPServer(config)
        transport = StdioTransport(server)
        await transport.start()  # 阻塞直到 stdin EOF
    """

    def __init__(self, server: MCPServer) -> None:
        self._server = server

    async def start(self) -> None:
        """启动 Stdio 处理循环"""
        await self._server.startup()
        logger.info("Stdio 传输已启动")

        loop = asyncio.get_running_loop()

        try:
            while True:
                # 在 executor 中读取 stdin（避免阻塞事件循环）
                line = await loop.run_in_executor(None, sys.stdin.readline)

                if not line:
                    break  # EOF

                line = line.strip()
                if not line:
                    continue

                response = await self._server.handle_request(line)

                if response:
                    sys.stdout.write(response + "\n")
                    sys.stdout.flush()

        except (KeyboardInterrupt, EOFError):
            pass
        except Exception:
            logger.exception("Stdio 处理异常")
        finally:
            await self._server.shutdown()
            logger.info("Stdio 传输已关闭")


# ═══════════════════════════════════════════════════════
#  工厂函数
# ═══════════════════════════════════════════════════════

def create_transport(
    server: MCPServer,
    transport_type: str = "tcp",
    **kwargs: Any,
) -> TCPTransport | StdioTransport:
    """
    根据配置创建传输层实例

    Args:
        server: MCPServer 实例
        transport_type: "tcp" 或 "stdio"
        **kwargs: 传输参数 (host, port 等)

    Returns:
        传输层实例
    """
    if transport_type == "tcp":
        return TCPTransport(
            server,
            host=kwargs.get("host", server.config.server.host),
            port=kwargs.get("port", server.config.server.port),
        )
    elif transport_type == "stdio":
        return StdioTransport(server)
    else:
        raise ValueError(f"不支持的传输类型: {transport_type}")
