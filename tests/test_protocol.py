"""
Layer 6: Protocol 完整测试

覆盖:
1. protocol/jsonrpc.py — JSON-RPC 2.0 解析、响应构造、错误映射
2. protocol/router.py — 方法路由器注册、解析、签名提取
3. protocol/server.py — MCPServer 请求调度、生命周期
4. 集成: 完整的请求→响应链路
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

passed = 0
failed = 0


def test(name, fn):
    global passed, failed
    try:
        if asyncio.iscoroutinefunction(fn):
            asyncio.get_event_loop().run_until_complete(fn())
        else:
            fn()
        print(f"  ✓ {name}")
        passed += 1
    except Exception as e:
        print(f"  ✗ {name}: {e}")
        failed += 1


# ═══════════════════════════════════════════
#  1. protocol/jsonrpc.py — JSON-RPC 2.0
# ═══════════════════════════════════════════
print("\n=== protocol/jsonrpc.py — JSON-RPC 2.0 ===")

from src.protocol.jsonrpc import (
    PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR,
    MCP_ERROR, MCP_RATE_LIMIT, MCP_PERMISSION,
    JsonRpcRequest, JsonRpcError,
    parse_request, success_response, error_response, batch_response,
    map_mcp_error, map_internal_error,
)


def test_parse_valid_request():
    """正常 JSON-RPC 2.0 请求"""
    raw = json.dumps({
        "jsonrpc": "2.0",
        "method": "read_file",
        "params": {"path": "/test.txt"},
        "id": 1,
    })
    result = parse_request(raw)
    assert isinstance(result, JsonRpcRequest)
    assert result.method == "read_file"
    assert result.params == {"path": "/test.txt"}
    assert result.id == 1
    assert not result.is_notification
test("解析: 正常请求", test_parse_valid_request)


def test_parse_notification():
    """通知请求（无 id）"""
    raw = json.dumps({
        "jsonrpc": "2.0",
        "method": "ping",
    })
    result = parse_request(raw)
    assert isinstance(result, JsonRpcRequest)
    assert result.is_notification
    assert result.id is None
test("解析: 通知请求", test_parse_notification)


def test_parse_no_params():
    """无 params 字段"""
    raw = json.dumps({"jsonrpc": "2.0", "method": "ping", "id": 1})
    result = parse_request(raw)
    assert isinstance(result, JsonRpcRequest)
    assert result.params == {}
test("解析: 无 params", test_parse_no_params)


def test_parse_invalid_json():
    """非法 JSON"""
    result = parse_request("{invalid")
    assert isinstance(result, JsonRpcError)
    assert result.code == PARSE_ERROR
test("解析: 非法 JSON", test_parse_invalid_json)


def test_parse_missing_jsonrpc():
    """缺少 jsonrpc 字段"""
    raw = json.dumps({"method": "ping", "id": 1})
    result = parse_request(raw)
    assert isinstance(result, JsonRpcError)
    assert result.code == INVALID_REQUEST
test("解析: 缺少 jsonrpc", test_parse_missing_jsonrpc)


def test_parse_missing_method():
    """缺少 method 字段"""
    raw = json.dumps({"jsonrpc": "2.0", "id": 1})
    result = parse_request(raw)
    assert isinstance(result, JsonRpcError)
    assert result.code == INVALID_REQUEST
test("解析: 缺少 method", test_parse_missing_method)


def test_parse_positional_params():
    """位置参数被拒绝"""
    raw = json.dumps({"jsonrpc": "2.0", "method": "test", "params": [1, 2], "id": 1})
    result = parse_request(raw)
    assert isinstance(result, JsonRpcError)
    assert result.code == INVALID_PARAMS
test("解析: 位置参数拒绝", test_parse_positional_params)


def test_parse_batch():
    """批量请求"""
    raw = json.dumps([
        {"jsonrpc": "2.0", "method": "ping", "id": 1},
        {"jsonrpc": "2.0", "method": "get_version", "id": 2},
    ])
    result = parse_request(raw)
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0].method == "ping"
    assert result[1].method == "get_version"
test("解析: 批量请求", test_parse_batch)


def test_parse_empty_batch():
    """空批量请求"""
    result = parse_request("[]")
    assert isinstance(result, JsonRpcError)
    assert result.code == INVALID_REQUEST
test("解析: 空批量拒绝", test_parse_empty_batch)


def test_success_response():
    """成功响应"""
    resp = success_response(1, {"status": "ok"})
    data = json.loads(resp)
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    assert data["result"]["status"] == "ok"
    assert "error" not in data
test("响应: 成功", test_success_response)


def test_success_with_warnings():
    """成功响应含警告"""
    warnings = [{"code": "SLOW", "message": "slow op"}]
    resp = success_response(1, {"status": "ok"}, warnings)
    data = json.loads(resp)
    assert "_warnings" in data["result"]
    assert data["result"]["_warnings"][0]["code"] == "SLOW"
test("响应: 成功+警告", test_success_with_warnings)


def test_error_response():
    """错误响应"""
    err = JsonRpcError(code=METHOD_NOT_FOUND, message="no such method")
    resp = error_response(1, err)
    data = json.loads(resp)
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    assert data["error"]["code"] == METHOD_NOT_FOUND
    assert "result" not in data
test("响应: 错误", test_error_response)


def test_batch_response():
    """批量响应"""
    r1 = success_response(1, {"a": 1})
    r2 = error_response(2, JsonRpcError(code=-32600, message="bad"))
    resp = batch_response([r1, r2])
    data = json.loads(resp)
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["id"] == 1
    assert "result" in data[0]
    assert data[1]["id"] == 2
    assert "error" in data[1]
test("响应: 批量", test_batch_response)


def test_map_mcp_error():
    """MCPError 映射"""
    from src.core.errors import (
        InvalidParameterError, BlockedPathError,
        RateLimitError, MaxConcurrentTasksError,
        FileNotFoundError,
    )
    # InvalidParameterError → INVALID_PARAMS
    e = map_mcp_error(InvalidParameterError("bad param"))
    assert e.code == INVALID_PARAMS

    # 403 错误 → MCP_PERMISSION
    e = map_mcp_error(BlockedPathError("blocked"))
    assert e.code == MCP_PERMISSION

    # RateLimitError → MCP_RATE_LIMIT
    e = map_mcp_error(RateLimitError("too fast"))
    assert e.code == MCP_RATE_LIMIT

    # MaxConcurrentTasksError → MCP_RATE_LIMIT
    e = map_mcp_error(MaxConcurrentTasksError("too many"))
    assert e.code == MCP_RATE_LIMIT

    # 其他 → MCP_ERROR
    e = map_mcp_error(FileNotFoundError("not found"))
    assert e.code == MCP_ERROR
test("MCPError → JSONRPC 映射", test_map_mcp_error)


def test_map_internal_error():
    """内部错误映射"""
    e = map_internal_error(RuntimeError("boom"))
    assert e.code == INTERNAL_ERROR
    assert "RuntimeError" in e.message
    assert e.data["type"] == "RuntimeError"
test("内部错误映射", test_map_internal_error)


# ═══════════════════════════════════════════
#  2. protocol/router.py — MethodRouter
# ═══════════════════════════════════════════
print("\n=== protocol/router.py — MethodRouter ===")

from src.protocol.router import MethodRouter
from src.handlers.base import RequestContext


class _FakeHandler:
    """测试用 handler"""

    async def greet(self, ctx: RequestContext, name: str, loud: bool = False) -> dict:
        msg = f"Hello, {name}!"
        if loud:
            msg = msg.upper()
        return {"message": msg}

    async def noop(self, ctx: RequestContext) -> dict:
        return {"ok": True}


def test_router_register_resolve():
    """注册和解析"""
    router = MethodRouter()
    handler = _FakeHandler()
    router.register("greet", handler.greet)

    assert "greet" in router
    assert router.resolve("greet") is not None
    assert router.resolve("unknown") is None
    assert router.method_count == 1
test("路由: 注册和解析", test_router_register_resolve)


async def test_router_call():
    """wrapped handler 调用"""
    router = MethodRouter()
    handler = _FakeHandler()
    router.register("greet", handler.greet)

    fn = router.resolve("greet")
    ctx = RequestContext(method="greet", params={"name": "World", "loud": True})
    result = await fn(ctx)
    assert result["message"] == "HELLO, WORLD!"
test("路由: 调用执行", test_router_call)


async def test_router_default_params():
    """可选参数默认值"""
    router = MethodRouter()
    handler = _FakeHandler()
    router.register("greet", handler.greet)

    fn = router.resolve("greet")
    ctx = RequestContext(method="greet", params={"name": "World"})
    result = await fn(ctx)
    assert result["message"] == "Hello, World!"
test("路由: 可选参数默认值", test_router_default_params)


def test_router_register_handler():
    """批量注册"""
    router = MethodRouter()
    handler = _FakeHandler()
    router.register_handler(handler, {
        "greet": "greet",
        "noop": "noop",
    })

    assert router.method_count == 2
    assert "greet" in router.methods
    assert "noop" in router.methods
test("路由: 批量注册", test_router_register_handler)


def test_router_methods_sorted():
    """方法列表排序"""
    router = MethodRouter()
    handler = _FakeHandler()
    router.register("z_method", handler.noop)
    router.register("a_method", handler.noop)

    assert router.methods == ["a_method", "z_method"]
test("路由: 排序", test_router_methods_sorted)


def test_router_signature():
    """方法签名提取"""
    router = MethodRouter()
    handler = _FakeHandler()
    router.register("greet", handler.greet)

    sig = router.get_method_signature("greet")
    assert sig is not None
    assert "name" in sig["params"]
    assert sig["params"]["name"]["required"] is True
    assert sig["params"]["loud"]["required"] is False
    assert sig["params"]["loud"]["default"] is False
test("路由: 签名提取", test_router_signature)


def test_router_invalid_register():
    """注册不存在的方法报错"""
    router = MethodRouter()
    handler = _FakeHandler()
    try:
        router.register_handler(handler, {"bad": "nonexistent"})
        assert False
    except ValueError as e:
        assert "nonexistent" in str(e)
test("路由: 无效注册报错", test_router_invalid_register)


def test_router_repr():
    """repr"""
    router = MethodRouter()
    assert "0 methods" in repr(router)
    router.register("test", _FakeHandler().noop)
    assert "1 methods" in repr(router)
test("路由: repr", test_router_repr)


# ═══════════════════════════════════════════
#  3. protocol/server.py — MCPServer
# ═══════════════════════════════════════════
print("\n=== protocol/server.py — MCPServer ===")

from src.protocol.server import MCPServer
from src.core.config import MCPConfig


async def test_server_init():
    """MCPServer 初始化"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = MCPConfig(workspace={"root_path": tmpdir})
        server = MCPServer(config)

        assert not server.is_running
        assert server.router.method_count == 36  # 16+3+10+7
        assert "read_file" in server.router
        assert "ping" in server.router
        assert "run_command" in server.router
        assert "find_files" in server.router
test("MCPServer: 初始化", test_server_init)


async def test_server_ping():
    """ping 请求端到端"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = MCPConfig(workspace={"root_path": tmpdir})
        server = MCPServer(config)

        req = json.dumps({
            "jsonrpc": "2.0",
            "method": "ping",
            "id": 1,
        })
        resp = await server.handle_request(req)
        data = json.loads(resp)

        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        assert "result" in data
        assert data["result"]["status"] == "ok"
        assert "uptime_seconds" in data["result"]
test("MCPServer: ping", test_server_ping)


async def test_server_get_version():
    """get_version 端到端"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = MCPConfig(workspace={"root_path": tmpdir})
        server = MCPServer(config)

        req = json.dumps({
            "jsonrpc": "2.0",
            "method": "get_version",
            "id": 2,
        })
        resp = await server.handle_request(req)
        data = json.loads(resp)
        assert data["result"]["version"] == "0.1.0"
test("MCPServer: get_version", test_server_get_version)


async def test_server_get_methods():
    """get_methods 返回全部方法列表"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = MCPConfig(workspace={"root_path": tmpdir})
        server = MCPServer(config)

        req = json.dumps({
            "jsonrpc": "2.0",
            "method": "get_methods",
            "id": 3,
        })
        resp = await server.handle_request(req)
        data = json.loads(resp)
        methods = data["result"]["methods"]
        assert "ping" in methods
        assert "read_file" in methods
        assert data["result"]["total"] == 36
test("MCPServer: get_methods", test_server_get_methods)


async def test_server_method_not_found():
    """未知方法返回 METHOD_NOT_FOUND"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = MCPConfig(workspace={"root_path": tmpdir})
        server = MCPServer(config)

        req = json.dumps({
            "jsonrpc": "2.0",
            "method": "nonexistent",
            "id": 4,
        })
        resp = await server.handle_request(req)
        data = json.loads(resp)
        assert data["error"]["code"] == METHOD_NOT_FOUND
test("MCPServer: 方法不存在", test_server_method_not_found)


async def test_server_parse_error():
    """JSON 解析失败"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = MCPConfig(workspace={"root_path": tmpdir})
        server = MCPServer(config)

        resp = await server.handle_request("{invalid json")
        data = json.loads(resp)
        assert data["error"]["code"] == PARSE_ERROR
test("MCPServer: JSON 解析失败", test_server_parse_error)


async def test_server_invalid_request():
    """非法 JSON-RPC 格式"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = MCPConfig(workspace={"root_path": tmpdir})
        server = MCPServer(config)

        req = json.dumps({"method": "ping"})  # 缺少 jsonrpc
        resp = await server.handle_request(req)
        data = json.loads(resp)
        assert data["error"]["code"] == INVALID_REQUEST
test("MCPServer: 非法请求格式", test_server_invalid_request)


async def test_server_notification():
    """通知请求返回空字符串"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = MCPConfig(workspace={"root_path": tmpdir})
        server = MCPServer(config)

        req = json.dumps({
            "jsonrpc": "2.0",
            "method": "ping",
            # 没有 id = 通知
        })
        resp = await server.handle_request(req)
        assert resp == ""
test("MCPServer: 通知无响应", test_server_notification)


async def test_server_read_file():
    """实际文件读取"""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "hello.txt"
        test_file.write_text("Hello World!", encoding="utf-8")

        config = MCPConfig(workspace={"root_path": tmpdir})
        server = MCPServer(config)

        req = json.dumps({
            "jsonrpc": "2.0",
            "method": "read_file",
            "params": {"path": str(test_file)},
            "id": 10,
        })
        resp = await server.handle_request(req)
        data = json.loads(resp)
        assert "result" in data
        assert data["result"]["content"] == "Hello World!"
test("MCPServer: read_file", test_server_read_file)


async def test_server_batch():
    """批量请求"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = MCPConfig(workspace={"root_path": tmpdir})
        server = MCPServer(config)

        req = json.dumps([
            {"jsonrpc": "2.0", "method": "ping", "id": 1},
            {"jsonrpc": "2.0", "method": "get_version", "id": 2},
        ])
        resp = await server.handle_request(req)
        data = json.loads(resp)
        assert isinstance(data, list)
        assert len(data) == 2
        ids = {d["id"] for d in data}
        assert ids == {1, 2}
test("MCPServer: 批量请求", test_server_batch)


async def test_server_lifecycle():
    """startup / shutdown"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = MCPConfig(workspace={"root_path": tmpdir})
        server = MCPServer(config)

        assert not server.is_running
        await server.startup()
        assert server.is_running
        await server.shutdown()
        assert not server.is_running
test("MCPServer: 生命周期", test_server_lifecycle)


async def test_server_security_block():
    """安全中间件拦截 workspace 外路径"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = MCPConfig(workspace={"root_path": tmpdir})
        server = MCPServer(config)

        req = json.dumps({
            "jsonrpc": "2.0",
            "method": "read_file",
            "params": {"path": "C:\\Windows\\System32\\cmd.exe"},
            "id": 20,
        })
        resp = await server.handle_request(req)
        data = json.loads(resp)
        assert "error" in data
        # 403 → MCP_PERMISSION
        assert data["error"]["code"] == MCP_PERMISSION
test("MCPServer: 安全拦截", test_server_security_block)


# ═══════════════════════════════════════════
#  4. protocol/transport.py — 传输工厂
# ═══════════════════════════════════════════
print("\n=== protocol/transport.py — 传输工厂 ===")

from src.protocol.transport import TCPTransport, StdioTransport, create_transport


def test_create_tcp_transport():
    """创建 TCP 传输"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = MCPConfig(workspace={"root_path": tmpdir})
        server = MCPServer(config)

        t = create_transport(server, "tcp")
        assert isinstance(t, TCPTransport)
test("传输: 创建 TCP", test_create_tcp_transport)


def test_create_stdio_transport():
    """创建 Stdio 传输"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = MCPConfig(workspace={"root_path": tmpdir})
        server = MCPServer(config)

        t = create_transport(server, "stdio")
        assert isinstance(t, StdioTransport)
test("传输: 创建 Stdio", test_create_stdio_transport)


def test_create_invalid_transport():
    """不支持的传输类型"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = MCPConfig(workspace={"root_path": tmpdir})
        server = MCPServer(config)

        try:
            create_transport(server, "websocket")
            assert False
        except ValueError as e:
            assert "websocket" in str(e)
test("传输: 无效类型报错", test_create_invalid_transport)


# ═══════════════════════════════════════════
#  5. 审计修复验证
# ═══════════════════════════════════════════
print("\n=== 审计修复验证 ===")


def test_fix_A_search_constants():
    """修复A: search.py 常量存在"""
    from src.handlers.search import _MAX_REGEX_LENGTH, _PER_FILE_TIMEOUT_S
    assert isinstance(_MAX_REGEX_LENGTH, int) and _MAX_REGEX_LENGTH > 0
    assert isinstance(_PER_FILE_TIMEOUT_S, float) and _PER_FILE_TIMEOUT_S > 0
test("修复A: search 常量定义", test_fix_A_search_constants)


def test_fix_B_validation_find_methods():
    """修复B: validation schema 使用 find_* 而非 search_*"""
    from src.middleware.validation import _METHOD_SCHEMAS
    assert "find_files" in _METHOD_SCHEMAS, "缺少 find_files"
    assert "find_content" in _METHOD_SCHEMAS, "缺少 find_content"
    assert "find_symbol" in _METHOD_SCHEMAS, "缺少 find_symbol"
    assert "search_files" not in _METHOD_SCHEMAS, "残留 search_files"
    assert "search_content" not in _METHOD_SCHEMAS, "残留 search_content"
    assert "search_symbol" not in _METHOD_SCHEMAS, "残留 search_symbol"
test("修复B: validation schema find_*", test_fix_B_validation_find_methods)


def test_fix_C_validation_task_status():
    """修复C: validation schema 有 task_status 无 get_task"""
    from src.middleware.validation import _METHOD_SCHEMAS
    assert "task_status" in _METHOD_SCHEMAS, "缺少 task_status"
    assert "get_task" not in _METHOD_SCHEMAS, "残留 get_task"
test("修复C: validation schema task_status", test_fix_C_validation_task_status)


async def test_fix_D_router_optional_path():
    """修复D: router 处理 Path | None 类型"""
    router = MethodRouter()
    handler = _FakeHandler()

    # 创建一个带 Path | None 参数的测试方法
    class _PathNoneHandler:
        async def search(self, ctx: RequestContext, root: Path | None = None) -> dict:
            return {"root_type": type(root).__name__, "root": str(root) if root else None}

    h = _PathNoneHandler()
    router.register("test_search", h.search)
    fn = router.resolve("test_search")

    # 传 string → 应自动转为 Path
    ctx = RequestContext(method="test_search", params={"root": "/some/path"})
    result = await fn(ctx)
    assert result["root_type"] == "WindowsPath" or result["root_type"] == "PosixPath", \
        f"Expected Path type, got {result['root_type']}"
test("修复D: router Path|None 转换", test_fix_D_router_optional_path)


async def test_fix_D_find_files_integration():
    """修复D: find_files 端到端（搜索API可调用）"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试文件
        test_file = Path(tmpdir) / "hello.py"
        test_file.write_text("print('hello')", encoding="utf-8")

        config = MCPConfig(workspace={"root_path": tmpdir})
        server = MCPServer(config)

        req = json.dumps({
            "jsonrpc": "2.0",
            "method": "find_files",
            "params": {"pattern": "*.py"},
            "id": 100,
        })
        resp = await server.handle_request(req)
        data = json.loads(resp)
        assert "result" in data, f"Expected result, got: {data}"
        assert data["result"]["total"] >= 1
test("修复D: find_files 端到端", test_fix_D_find_files_integration)


# ═══════════════════════════════════════════
#  汇总
# ═══════════════════════════════════════════
print(f"\n{'='*40}")
print(f"通过: {passed}, 失败: {failed}")
if failed:
    print("有测试失败!")
    sys.exit(1)
else:
    print("全部通过!")
