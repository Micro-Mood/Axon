"""
Layer 6: Protocol — JSON-RPC 2.0 编解码器

职责:
- 解析 JSON-RPC 2.0 请求（单条 & 批量）
- 构造 JSON-RPC 2.0 响应（成功 & 错误）
- 标准错误码定义
- MCPError → JSON-RPC error 映射

规范参考: https://www.jsonrpc.org/specification

依赖:
- Layer 1: core/errors (MCPError, 各子类)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ..core.errors import (
    MCPError,
    InvalidParameterError,
    MaxConcurrentTasksError,
    RateLimitError,
)


# ═══════════════════════════════════════════════════════
#  JSON-RPC 2.0 标准错误码
# ═══════════════════════════════════════════════════════

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# 应用自定义码区间: -32000 ~ -32099
MCP_ERROR = -32000
MCP_RATE_LIMIT = -32001
MCP_PERMISSION = -32002


# ═══════════════════════════════════════════════════════
#  请求 / 响应 数据类
# ═══════════════════════════════════════════════════════

@dataclass
class JsonRpcRequest:
    """解析后的 JSON-RPC 2.0 请求"""
    method: str
    params: dict[str, Any] = field(default_factory=dict)
    id: int | str | None = None  # None = 通知（不需要响应）
    is_notification: bool = False


@dataclass
class JsonRpcError:
    """JSON-RPC 2.0 错误对象"""
    code: int
    message: str
    data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.data is not None:
            d["data"] = self.data
        return d


# ═══════════════════════════════════════════════════════
#  解析器
# ═══════════════════════════════════════════════════════

def parse_request(raw: str | bytes) -> JsonRpcRequest | list[JsonRpcRequest] | JsonRpcError:
    """
    解析 JSON-RPC 2.0 请求

    Returns:
        - JsonRpcRequest: 单条请求
        - list[JsonRpcRequest]: 批量请求
        - JsonRpcError: 解析失败

    不抛异常，错误通过返回值传递。
    """
    # JSON 解码
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return JsonRpcError(
            code=PARSE_ERROR,
            message=f"JSON 解析失败: {e}",
        )

    # 批量请求
    if isinstance(data, list):
        if not data:
            return JsonRpcError(
                code=INVALID_REQUEST,
                message="批量请求不能为空数组",
            )
        results = [_parse_single(item) for item in data]
        # 如果所有都解析失败，返回第一个错误
        errors = [r for r in results if isinstance(r, JsonRpcError)]
        if len(errors) == len(results):
            return errors[0]
        return [r for r in results if isinstance(r, JsonRpcRequest)]

    # 单条请求
    if isinstance(data, dict):
        return _parse_single(data)

    return JsonRpcError(
        code=INVALID_REQUEST,
        message="请求必须是 JSON 对象或数组",
    )


def _parse_single(data: Any) -> JsonRpcRequest | JsonRpcError:
    """解析单条 JSON-RPC 2.0 请求"""
    if not isinstance(data, dict):
        return JsonRpcError(
            code=INVALID_REQUEST,
            message="请求必须是 JSON 对象",
        )

    # jsonrpc 版本检查
    if data.get("jsonrpc") != "2.0":
        return JsonRpcError(
            code=INVALID_REQUEST,
            message="jsonrpc 字段必须为 \"2.0\"",
        )

    # method 必须是字符串
    method = data.get("method")
    if not isinstance(method, str) or not method:
        return JsonRpcError(
            code=INVALID_REQUEST,
            message="method 字段必须是非空字符串",
        )

    # params 可选，必须是 dict 或 list（我们只支持 dict）
    params = data.get("params", {})
    if isinstance(params, list):
        # 位置参数不支持，转为命名参数的通用做法不可靠
        return JsonRpcError(
            code=INVALID_PARAMS,
            message="仅支持命名参数 (params 必须是 object)",
        )
    if not isinstance(params, dict):
        return JsonRpcError(
            code=INVALID_PARAMS,
            message="params 必须是 object 或省略",
        )

    # id 可选（无 id = 通知）
    request_id = data.get("id")
    is_notification = "id" not in data

    return JsonRpcRequest(
        method=method,
        params=params,
        id=request_id,
        is_notification=is_notification,
    )


# ═══════════════════════════════════════════════════════
#  响应构造
# ═══════════════════════════════════════════════════════

def success_response(
    request_id: int | str | None,
    result: dict[str, Any],
    warnings: list[dict[str, Any]] | None = None,
) -> str:
    """
    构造成功响应

    Args:
        request_id: 请求 ID
        result: handler 返回的结果 dict
        warnings: 请求级别警告列表

    Returns:
        JSON 字符串
    """
    payload: dict[str, Any] = result
    if warnings:
        payload = {**result, "_warnings": warnings}

    response: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": payload,
    }
    return json.dumps(response, ensure_ascii=False, default=str)


def error_response(
    request_id: int | str | None,
    error: JsonRpcError,
) -> str:
    """
    构造错误响应

    Args:
        request_id: 请求 ID（解析失败时可能为 None）
        error: JSON-RPC 错误对象

    Returns:
        JSON 字符串
    """
    response: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": error.to_dict(),
    }
    return json.dumps(response, ensure_ascii=False, default=str)


def batch_response(responses: list[str]) -> str:
    """
    构造批量响应

    Args:
        responses: 各个子响应的 JSON 字符串列表

    Returns:
        JSON 数组字符串
    """
    # 每个元素已经是 JSON 字符串，解析后拼成数组
    parsed = [json.loads(r) for r in responses]
    return json.dumps(parsed, ensure_ascii=False, default=str)


# ═══════════════════════════════════════════════════════
#  MCPError → JSON-RPC Error 映射
# ═══════════════════════════════════════════════════════

def map_mcp_error(exc: MCPError) -> JsonRpcError:
    """
    将 MCPError 子类映射为 JSON-RPC 错误

    映射规则:
    - InvalidParameterError → INVALID_PARAMS (-32602)
    - RateLimitError / MaxConcurrentTasksError → MCP_RATE_LIMIT (-32001)
    - 403 类错误 → MCP_PERMISSION (-32002)
    - 其他 MCPError → MCP_ERROR (-32000)
    """
    code = MCP_ERROR

    if isinstance(exc, InvalidParameterError):
        code = INVALID_PARAMS
    elif isinstance(exc, (RateLimitError, MaxConcurrentTasksError)):
        code = MCP_RATE_LIMIT
    elif exc.http_status == 403:
        code = MCP_PERMISSION

    return JsonRpcError(
        code=code,
        message=exc.message,
        data=exc.to_dict(),
    )


def map_internal_error(exc: Exception) -> JsonRpcError:
    """将未预期的异常映射为 INTERNAL_ERROR"""
    return JsonRpcError(
        code=INTERNAL_ERROR,
        message=f"内部错误: {type(exc).__name__}",
        # 不泄露完整堆栈给客户端，仅类型和简短消息
        data={
            "type": type(exc).__name__,
            "message": str(exc)[:500],
        },
    )
