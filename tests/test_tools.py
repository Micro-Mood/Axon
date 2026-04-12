"""
Tools 插件系统测试

覆盖:
1. tools/__init__.py — ToolDef、发现机制、查询辅助
2. 各 tool 文件 — ToolDef 元数据完整性
3. 集成 — discover_all → middleware → router 端到端
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
#  1. tools/__init__.py — 基础设施
# ═══════════════════════════════════════════
print("\n=== tools/__init__.py — 基础设施 ===")

from src.tools import (
    ToolDef, Param, param,
    STR, INT, BOOL, STR_OR_NONE, INT_OR_NONE, PATH,
    discover_all, load_tools_from_package,
    methods_by_lock, write_methods, track_methods, get_params,
)


def test_param_basic():
    """param() 快捷构建"""
    p = param("path", STR, non_empty=True)
    assert p.name == "path"
    assert p.type == STR
    assert p.required is True
    assert p.non_empty is True
    assert p.default is None

test("param() 快捷构建", test_param_basic)


def test_param_optional():
    """param() 可选参数"""
    p = param("encoding", STR_OR_NONE, required=False, default="utf-8")
    assert p.required is False
    assert p.default == "utf-8"
    assert p.type == STR_OR_NONE

test("param() 可选参数", test_param_optional)


def test_tooldef_defaults():
    """ToolDef 默认值"""
    t = ToolDef(name="test")
    assert t.lock == "none"
    assert t.track is None
    assert t.is_write is False
    assert t.params == []
    assert t.execute is None
    assert t.group == ""

test("ToolDef 默认值", test_tooldef_defaults)


# ═══════════════════════════════════════════
#  2. discover_all — 扫描全部 tools
# ═══════════════════════════════════════════
print("\n=== discover_all — 扫描全部 tools ===")

ALL_TOOLS = discover_all()


def test_discover_count():
    """应发现 27 个 tool"""
    assert len(ALL_TOOLS) == 27, f"期望 27 个 tool，实际 {len(ALL_TOOLS)}"

test("发现 27 个 tool", test_discover_count)


def test_discover_groups():
    """5 个 group: file(12), search(3), command(10), system(1), web(1)"""
    groups = {}
    for t in ALL_TOOLS.values():
        groups.setdefault(t.group, []).append(t.name)

    assert len(groups["file"]) == 12, f"file 应有12 个: {groups.get('file')}"
    assert len(groups["search"]) == 3, f"search 应有3 个: {groups.get('search')}"
    assert len(groups["command"]) == 10, f"command 应有10 个: {groups.get('command')}"
    assert len(groups["system"]) == 1, f"system 应有1 个: {groups.get('system')}"
    assert len(groups["web"]) == 1, f"web 应有 1 个: {groups.get('web')}"

test("5 个 group 数量正确", test_discover_groups)


def test_discover_all_have_execute():
    """所有 tool 都有 execute 函数"""
    for name, t in ALL_TOOLS.items():
        assert t.execute is not None, f"{name} 缺少 execute"
        assert callable(t.execute), f"{name}.execute 不可调用"

test("所有 tool 有 execute", test_discover_all_have_execute)


def test_discover_all_have_name():
    """所有 tool 的 name 与 dict key 一致"""
    for key, t in ALL_TOOLS.items():
        assert key == t.name, f"key={key} != t.name={t.name}"

test("name 与 key 一致", test_discover_all_have_name)


# ═══════════════════════════════════════════
#  3. ToolDef 元数据完整性
# ═══════════════════════════════════════════
print("\n=== ToolDef 元数据完整性 ===")

EXPECTED_TOOLS = {
    # File read
    "read_file": {"lock": "read", "is_write": False, "group": "file"},
    "stat_path": {"lock": "read", "is_write": False, "group": "file"},
    "list_directory": {"lock": "none", "is_write": False, "group": "file"},
    # File write
    "write_file": {"lock": "write", "is_write": True, "group": "file"},
    "create_directory": {"lock": "dir_write", "is_write": True, "group": "file"},
    "replace_string_in_file": {"lock": "write", "is_write": True, "group": "file"},
    "multi_replace_string_in_file": {"lock": "write", "is_write": True, "group": "file"},
    "delete_file": {"lock": "write", "is_write": True, "group": "file"},
    # File move
    "move_file": {"lock": "write_dual", "is_write": True, "group": "file"},
    "copy_file": {"lock": "write_dual", "is_write": True, "group": "file"},
    # Directory
    "move_directory": {"lock": "dir_write", "is_write": True, "group": "file"},
    "delete_directory": {"lock": "dir_write", "is_write": True, "group": "file"},
    # Search
    "find_files": {"lock": "none", "is_write": False, "group": "search"},
    "search_text": {"lock": "none", "is_write": False, "group": "search"},
    "find_symbol": {"lock": "none", "is_write": False, "group": "search"},
    # Command
    "run_command": {"lock": "none", "is_write": False, "track": None, "group": "command"},
    "create_task": {"lock": "none", "is_write": False, "track": "task_create", "group": "command"},
    "stop_task": {"lock": "none", "is_write": False, "track": "task_end", "group": "command"},
    "del_task": {"lock": "none", "is_write": False, "group": "command"},
    "task_status": {"lock": "none", "is_write": False, "group": "command"},
    "wait_task": {"lock": "none", "is_write": False, "group": "command"},
    "list_tasks": {"lock": "none", "is_write": False, "group": "command"},
    "read_stdout": {"lock": "none", "is_write": False, "group": "command"},
    "read_stderr": {"lock": "none", "is_write": False, "group": "command"},
    "write_stdin": {"lock": "none", "is_write": False, "group": "command"},
    # System
    "get_system_info": {"lock": "none", "is_write": False, "group": "system"},
    # Web
    "fetch_webpage": {"lock": "none", "is_write": False, "group": "web"},
}


def test_all_expected_tools_exist():
    """所有预期 tool 都被发现"""
    missing = set(EXPECTED_TOOLS.keys()) - set(ALL_TOOLS.keys())
    assert not missing, f"缺少: {missing}"

test("所有预期 tool 都存在", test_all_expected_tools_exist)


def test_metadata_lock_is_write():
    """lock 和 is_write 元数据正确"""
    for name, expected in EXPECTED_TOOLS.items():
        t = ALL_TOOLS[name]
        assert t.lock == expected["lock"], f"{name}: lock={t.lock}, 期望 {expected['lock']}"
        assert t.is_write == expected["is_write"], f"{name}: is_write={t.is_write}, 期望 {expected['is_write']}"

test("lock 和 is_write 正确", test_metadata_lock_is_write)


def test_metadata_track():
    """task tracking 元数据正确"""
    assert ALL_TOOLS["create_task"].track == "task_create"
    assert ALL_TOOLS["stop_task"].track == "task_end"
    # 其他 command 工具不追踪
    for name in ["run_command", "del_task", "task_status", "wait_task", "list_tasks", "read_stdout", "read_stderr", "write_stdin"]:
        assert ALL_TOOLS[name].track is None, f"{name} 不应有 track"

test("track 元数据正确", test_metadata_track)


def test_metadata_groups():
    """group 元数据正确"""
    for name, expected in EXPECTED_TOOLS.items():
        assert ALL_TOOLS[name].group == expected["group"], \
            f"{name}: group={ALL_TOOLS[name].group}, 期望 {expected['group']}"

test("group 元数据正确", test_metadata_groups)


# ═══════════════════════════════════════════
#  4. 查询辅助函数
# ═══════════════════════════════════════════
print("\n=== 查询辅助函数 ===")


def test_methods_by_lock():
    """按 lock 类型过滤"""
    reads = methods_by_lock(ALL_TOOLS, "read")
    assert "read_file" in reads
    assert "stat_path" in reads
    assert "replace_string_in_file" not in reads

    writes = methods_by_lock(ALL_TOOLS, "write")
    assert "replace_string_in_file" in writes
    assert "write_file" in writes
    assert "read_file" not in writes

    duals = methods_by_lock(ALL_TOOLS, "write_dual")
    assert "move_file" in duals
    assert "copy_file" in duals
    assert len(duals) == 2

test("methods_by_lock", test_methods_by_lock)


def test_write_methods():
    """写操作方法集"""
    wm = write_methods(ALL_TOOLS)
    assert len(wm) == 9  # 9 file write tools
    assert "replace_string_in_file" in wm
    assert "multi_replace_string_in_file" in wm
    assert "read_file" not in wm
    assert "get_system_info" not in wm

test("write_methods", test_write_methods)


def test_track_methods():
    """任务追踪方法集"""
    creates = track_methods(ALL_TOOLS, "task_create")
    assert creates == frozenset({"create_task"})

    ends = track_methods(ALL_TOOLS, "task_end")
    assert ends == frozenset({"stop_task"})

test("track_methods", test_track_methods)


def test_get_params():
    """参数字典"""
    params_map = get_params(ALL_TOOLS)
    assert len(params_map) == 27

    # read_file 有4 个参数
    rf = params_map["read_file"]
    assert len(rf) == 4
    names = {p.name for p in rf}
    assert names == {"path", "encoding", "line_range", "max_size"}

    # get_system_info 没有参数
    assert params_map["get_system_info"] == []

test("get_params", test_get_params)


# ═══════════════════════════════════════════
#  5. 参数 schema 与原 validation.py 一致性
# ═══════════════════════════════════════════
print("\n=== 参数 schema 一致性 ===")

from src.middleware.validation import _METHOD_SCHEMAS


def test_schema_consistency():
    """tools 的参数与 _METHOD_SCHEMAS 完全一致"""
    tools_params = get_params(ALL_TOOLS)
    mismatches = []

    for method_name, old_params in _METHOD_SCHEMAS.items():
        if method_name not in tools_params:
            mismatches.append(f"{method_name}: 在 tools 中不存在")
            continue

        new_params = tools_params[method_name]
        if len(old_params) != len(new_params):
            mismatches.append(
                f"{method_name}: 参数数量不同 old={len(old_params)} new={len(new_params)}"
            )
            continue

        for old_p, new_p in zip(old_params, new_params):
            if old_p.name != new_p.name:
                mismatches.append(f"{method_name}: 参数名不同 {old_p.name} vs {new_p.name}")
            if old_p.type != new_p.type:
                mismatches.append(f"{method_name}.{old_p.name}: type 不同 {old_p.type} vs {new_p.type}")
            if old_p.required != new_p.required:
                mismatches.append(f"{method_name}.{old_p.name}: required 不同 {old_p.required} vs {new_p.required}")
            if old_p.default != new_p.default:
                mismatches.append(f"{method_name}.{old_p.name}: default 不同 {old_p.default!r} vs {new_p.default!r}")
            if old_p.non_empty != new_p.non_empty:
                mismatches.append(f"{method_name}.{old_p.name}: non_empty 不同 {old_p.non_empty} vs {new_p.non_empty}")
            if old_p.min_value != new_p.min_value:
                mismatches.append(f"{method_name}.{old_p.name}: min_value 不同 {old_p.min_value} vs {new_p.min_value}")
            if old_p.max_value != new_p.max_value:
                mismatches.append(f"{method_name}.{old_p.name}: max_value 不同 {old_p.max_value} vs {new_p.max_value}")

    assert not mismatches, "schema 不一致:\n  " + "\n  ".join(mismatches)

test("参数 schema 与 validation.py 完全一致", test_schema_consistency)


# ═══════════════════════════════════════════
#  6. 中间件方法集一致性
# ═══════════════════════════════════════════
print("\n=== 中间件方法集一致性 ===")


def test_security_write_methods_match():
    """SecurityMiddleware 内置常量与 tools 派生的 write_methods 一致"""
    from src.middleware.security import _WRITE_METHODS as SEC_WRITE
    tools_write = write_methods(ALL_TOOLS)
    assert tools_write == SEC_WRITE, f"差异: tools多={tools_write - SEC_WRITE}, 少={SEC_WRITE - tools_write}"

test("security write_methods 一致", test_security_write_methods_match)


def test_ratelimit_write_methods_match():
    """tools 的 is_write 与 rate_limit middleware 的 _WRITE_METHODS 一致"""
    from src.middleware.rate_limit import _WRITE_METHODS as RL_WRITE
    tools_write = write_methods(ALL_TOOLS)
    # rate_limit 多包含 set_workspace（限流用，非文件操作）
    assert tools_write | {"set_workspace"} == RL_WRITE, f"差异: tools多={tools_write - RL_WRITE}, 少={RL_WRITE - tools_write - {'set_workspace'}}"

test("rate_limit write_methods 一致", test_ratelimit_write_methods_match)


def test_concurrency_method_sets_match():
    """tools 的 lock/track 与 concurrency middleware 的方法集一致"""
    from src.middleware.concurrency import (
        _FILE_WRITE_METHODS, _FILE_MOVE_METHODS, _DIR_WRITE_METHODS,
        _FILE_READ_METHODS, _TASK_CREATE_METHODS, _TASK_END_METHODS,
    )

    assert methods_by_lock(ALL_TOOLS, "write") == _FILE_WRITE_METHODS, \
        f"file_write 差异"
    assert methods_by_lock(ALL_TOOLS, "write_dual") == _FILE_MOVE_METHODS, \
        f"file_move 差异"
    assert methods_by_lock(ALL_TOOLS, "dir_write") == _DIR_WRITE_METHODS, \
        f"dir_write 差异"
    assert methods_by_lock(ALL_TOOLS, "read") == _FILE_READ_METHODS, \
        f"file_read 差异: tools={methods_by_lock(ALL_TOOLS, 'read')}, old={_FILE_READ_METHODS}"
    assert track_methods(ALL_TOOLS, "task_create") == _TASK_CREATE_METHODS, \
        f"task_create 差异"
    assert track_methods(ALL_TOOLS, "task_end") == _TASK_END_METHODS, \
        f"task_end 差异"

test("concurrency 方法集一致", test_concurrency_method_sets_match)


# ═══════════════════════════════════════════
#  7. MCPServer 集成
# ═══════════════════════════════════════════
print("\n=== MCPServer 集成 ===")


def test_server_uses_tools():
    """MCPServer 使用 tools 自动注册"""
    from src.protocol.server import MCPServer
    with tempfile.TemporaryDirectory() as tmp:
        from src.core.config import MCPConfig
        config = MCPConfig(workspace={"root_path": tmp})
        server = MCPServer(config)

        # 33 个方法都已注册（27 个 AI 工具 + 6 个协议方法）
        methods = server._router.methods
        assert len(methods) == 33, f"期望 33 个方法，实际 {len(methods)}: {methods}"

        # 关键方法存在
        for name in ["read_file", "find_files", "run_command", "ping"]:
            assert name in methods, f"方法 {name} 未注册"

test("MCPServer 注册 33 个方法", test_server_uses_tools)


async def test_server_e2e_ping():
    """端到端: ping 通过 tools 注册可正常调用"""
    from src.protocol.server import MCPServer
    with tempfile.TemporaryDirectory() as tmp:
        from src.core.config import MCPConfig
        config = MCPConfig(workspace={"root_path": tmp})
        server = MCPServer(config)
        await server.startup()

        req = json.dumps({
            "jsonrpc": "2.0",
            "method": "ping",
            "id": 1,
            "params": {},
        })
        resp_str = await server.handle_request(req)
        resp = json.loads(resp_str)
        assert resp["result"]["status"] == "ok"
        await server.shutdown()

test("端到端: ping", test_server_e2e_ping)


async def test_server_e2e_read_file():
    """端到端: read_file 通过 tools 注册可正常调用"""
    from src.protocol.server import MCPServer
    with tempfile.TemporaryDirectory() as tmp:
        from src.core.config import MCPConfig
        config = MCPConfig(workspace={"root_path": tmp})
        server = MCPServer(config)
        await server.startup()

        # 创建测试文件
        test_file = Path(tmp) / "hello.txt"
        test_file.write_text("hello world\n", encoding="utf-8")

        req = json.dumps({
            "jsonrpc": "2.0",
            "method": "read_file",
            "id": 2,
            "params": {"path": str(test_file)},
        })
        resp_str = await server.handle_request(req)
        resp = json.loads(resp_str)
        assert "error" not in resp, f"错误: {resp.get('error')}"
        assert resp["result"]["content"] == "hello world\n"
        await server.shutdown()

test("端到端: read_file", test_server_e2e_read_file)


async def test_server_e2e_write_file():
    """端到端: write_file 写操作通过 tools 注册"""
    from src.protocol.server import MCPServer
    with tempfile.TemporaryDirectory() as tmp:
        from src.core.config import MCPConfig
        config = MCPConfig(workspace={"root_path": tmp})
        server = MCPServer(config)
        await server.startup()

        req = json.dumps({
            "jsonrpc": "2.0",
            "method": "write_file",
            "id": 3,
            "params": {
                "path": str(Path(tmp) / "new.txt"),
                "content": "created via tools",
            },
        })
        resp_str = await server.handle_request(req)
        resp = json.loads(resp_str)
        assert "error" not in resp, f"错误: {resp.get('error')}"
        assert resp["result"]["created"] is True

        # 验证文件确实被创建
        assert (Path(tmp) / "new.txt").read_text(encoding="utf-8") == "created via tools"
        await server.shutdown()

test("端到端: write_file", test_server_e2e_write_file)


async def test_server_e2e_find_files():
    """端到端: find_files 搜索通过 tools 注册"""
    from src.protocol.server import MCPServer
    with tempfile.TemporaryDirectory() as tmp:
        from src.core.config import MCPConfig
        config = MCPConfig(workspace={"root_path": tmp})
        server = MCPServer(config)
        await server.startup()

        # 创建测试文件
        (Path(tmp) / "test.py").write_text("pass\n")
        (Path(tmp) / "test.js").write_text("//\n")

        req = json.dumps({
            "jsonrpc": "2.0",
            "method": "find_files",
            "id": 4,
            "params": {"pattern": "*.py"},
        })
        resp_str = await server.handle_request(req)
        resp = json.loads(resp_str)
        assert "error" not in resp, f"错误: {resp.get('error')}"
        assert resp["result"]["total"] == 1
        await server.shutdown()

test("端到端: find_files", test_server_e2e_find_files)


# ═══════════════════════════════════════════
#  8. router.register_tool
# ═══════════════════════════════════════════
print("\n=== router.register_tool ===")


async def test_register_tool_basic():
    """register_tool 正确注册和调用"""
    from src.protocol.router import MethodRouter
    from src.handlers.base import RequestContext

    tool = ToolDef(
        name="test_tool",
        lock="none",
        params=[
            param("msg", STR),
            param("count", INT, required=False, default=1),
        ],
    )

    class FakeHandler:
        async def do_thing(self, ctx, msg="", count=1):
            return {"echo": msg, "count": count}

    handler = FakeHandler()

    async def execute(h, ctx, **kwargs):
        return await h.do_thing(ctx, **kwargs)

    tool.execute = execute

    router = MethodRouter()
    router.register_tool(tool, handler)

    assert "test_tool" in router
    fn = router.resolve("test_tool")

    ctx = RequestContext(method="test_tool", params={"msg": "hello", "count": 3})
    result = await fn(ctx)
    assert result == {"echo": "hello", "count": 3}

test("register_tool 注册和调用", test_register_tool_basic)


async def test_register_tool_path_conversion():
    """register_tool 自动 str→Path 转换"""
    from src.protocol.router import MethodRouter
    from src.handlers.base import RequestContext

    tool = ToolDef(
        name="test_path",
        params=[param("path", STR, non_empty=True)],
    )

    received_type = []

    async def execute(h, ctx, **kwargs):
        received_type.append(type(kwargs.get("path")))
        return {}

    tool.execute = execute

    router = MethodRouter()
    router.register_tool(tool, None)  # handler is None for this test

    ctx = RequestContext(method="test_path", params={"path": "/tmp/test.txt"})
    await router.resolve("test_path")(ctx)

    assert issubclass(received_type[0], Path), f"期望 Path 子类, 得到 {received_type[0]}"

test("register_tool str→Path 转换", test_register_tool_path_conversion)


# ═══════════════════════════════════════════
#  9. middleware 使用 tools 参数
# ═══════════════════════════════════════════
print("\n=== middleware 使用 tools 参数 ===")


async def test_validation_with_tools():
    """ValidationMiddleware 使用 tools 参数 schema"""
    from src.middleware.validation import ValidationMiddleware
    from src.handlers.base import RequestContext

    mw = ValidationMiddleware(tools=ALL_TOOLS)

    # 缺少必选参数
    ctx = RequestContext(method="read_file", params={})
    try:
        await mw(ctx, None)
        assert False, "应该抛异常"
    except Exception as e:
        assert "path" in str(e).lower() or "必选" in str(e)

test("ValidationMiddleware 用 tools schema 校验", test_validation_with_tools)


async def test_security_with_tools():
    """SecurityMiddleware 使用 tools 百則写操作"""
    from src.middleware.security import SecurityMiddleware
    from src.core.config import MCPConfig
    from src.core.security import SecurityChecker
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        config = MCPConfig(workspace={"root_path": tmp})
        security = SecurityChecker(config.security)
        mw = SecurityMiddleware(config, security, tools=ALL_TOOLS)
        # 写操作应在 write_methods 中
        assert "write_file" in mw._write_methods
        assert "replace_string_in_file" in mw._write_methods
        assert "read_file" not in mw._write_methods

test("SecurityMiddleware 用 tools 派生 write_methods", test_security_with_tools)


async def test_concurrency_with_tools():
    """ConcurrencyMiddleware 使用 tools 派生方法集"""
    from src.middleware.concurrency import ConcurrencyMiddleware

    mw = ConcurrencyMiddleware(tools=ALL_TOOLS)
    assert "replace_string_in_file" in mw._file_write
    assert "move_file" in mw._file_move
    assert "create_directory" in mw._dir_write
    assert "read_file" in mw._file_read
    assert "create_task" in mw._task_create
    assert "stop_task" in mw._task_end

test("ConcurrencyMiddleware 用 tools 派生方法集", test_concurrency_with_tools)


# ═══════════════════════════════════════════
#  10. 新增 tool 模拟
# ═══════════════════════════════════════════
print("\n=== 新增 tool 模拟（未来扩展验证）===")


def test_add_tool_only_needs_one_file():
    """
    验证架构: 新增 tool 只需一个 .py 文件定义 ToolDef + execute，
    无需修改 middleware 或 server 代码。
    """
    # 模拟一个新 tool
    new_tool = ToolDef(
        name="custom_operation",
        lock="write",
        is_write=True,
        track=None,
        params=[
            param("target", STR, non_empty=True),
            param("force", BOOL, required=False, default=False),
        ],
    )

    async def new_execute(handler, ctx, **kwargs):
        return {"result": "done"}

    new_tool.execute = new_execute
    new_tool.group = "file"

    # 合并到现有 tools
    extended_tools = dict(ALL_TOOLS)
    extended_tools["custom_operation"] = new_tool

    # 验证 middleware 自动识别新 tool
    assert "custom_operation" in write_methods(extended_tools)
    assert "custom_operation" in methods_by_lock(extended_tools, "write")

    # 验证 schema 可提取
    p = get_params(extended_tools)["custom_operation"]
    assert len(p) == 2
    assert p[0].name == "target"

test("新增 tool 零修改集成", test_add_tool_only_needs_one_file)


# ═══════════════════════════════════════════
print(f"\n{'=' * 40}")
print(f"通过: {passed}, 失败: {failed}")
if failed == 0:
    print("全部通过!")
else:
    print(f"有 {failed} 个失败!")
    sys.exit(1)
