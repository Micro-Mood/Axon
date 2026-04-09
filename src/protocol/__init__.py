"""
Layer 6: Protocol（协议层）

Axon MCP Server 的最外层，将 1~5 层串联为完整的 JSON-RPC 2.0 服务。

提供:
- MCPServer: 服务主体（初始化 + 请求调度 + 生命周期）
- MethodRouter: 方法路由器（method 名 → handler 映射）
- JSON-RPC 2.0 编解码器（解析请求、构造响应、错误映射）
- TCPTransport / StdioTransport: 传输层

架构位置:
    客户端 → Transport → MCPServer.handle_request
                            → parse_request (jsonrpc)
                            → MethodRouter.resolve (router)
                            → MiddlewareChain.execute (middleware)
                                → Handler 方法 (handlers)
                            → success_response / error_response (jsonrpc)
                        ← Transport → 客户端

依赖:
- Layer 1~5 全部
"""

from .jsonrpc import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    MCP_ERROR,
    MCP_PERMISSION,
    MCP_RATE_LIMIT,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    JsonRpcError,
    JsonRpcRequest,
    batch_response,
    error_response,
    map_internal_error,
    map_mcp_error,
    parse_request,
    success_response,
)
from .router import MethodRouter
from .server import MCPServer
from .transport import (
    StdioTransport,
    TCPTransport,
    create_transport,
)

__all__ = [
    # Server
    "MCPServer",
    # Router
    "MethodRouter",
    # JSON-RPC
    "JsonRpcRequest",
    "JsonRpcError",
    "parse_request",
    "success_response",
    "error_response",
    "batch_response",
    "map_mcp_error",
    "map_internal_error",
    # Error Codes
    "PARSE_ERROR",
    "INVALID_REQUEST",
    "METHOD_NOT_FOUND",
    "INVALID_PARAMS",
    "INTERNAL_ERROR",
    "MCP_ERROR",
    "MCP_RATE_LIMIT",
    "MCP_PERMISSION",
    # Transport
    "TCPTransport",
    "StdioTransport",
    "create_transport",
]
