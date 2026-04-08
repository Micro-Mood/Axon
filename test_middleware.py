"""Layer 5: Middleware 层完整测试"""
import asyncio
import sys
import time
sys.path.insert(0, ".")

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
#  chain.py 测试
# ═══════════════════════════════════════════
print("\n=== middleware/chain.py ===")

from src.middleware.chain import MiddlewareChain
from src.handlers.base import RequestContext

class AddHeaderMiddleware:
    async def __call__(self, ctx, next_handler):
        ctx.params["header_added"] = True
        result = await next_handler(ctx)
        result["post_processed"] = True
        return result

class MultiplyMiddleware:
    async def __call__(self, ctx, next_handler):
        ctx.params["multiplied"] = True
        return await next_handler(ctx)

async def dummy_handler(ctx):
    return {"status": "ok", "params": dict(ctx.params)}

async def test_chain_empty():
    chain = MiddlewareChain()
    ctx = RequestContext(method="test", params={"x": 1})
    result = await chain.execute(ctx, dummy_handler)
    assert result["status"] == "ok"
test("空链执行", test_chain_empty)

async def test_chain_single():
    chain = MiddlewareChain()
    chain.use(AddHeaderMiddleware())
    ctx = RequestContext(method="test", params={})
    result = await chain.execute(ctx, dummy_handler)
    assert result["post_processed"] == True
    assert result["params"]["header_added"] == True
test("单中间件", test_chain_single)

async def test_chain_order():
    """验证洋葱模型: 前置按注册顺序, 后置按逆序"""
    order = []
    class M1:
        async def __call__(self, ctx, next_h):
            order.append("M1-pre")
            r = await next_h(ctx)
            order.append("M1-post")
            return r
    class M2:
        async def __call__(self, ctx, next_h):
            order.append("M2-pre")
            r = await next_h(ctx)
            order.append("M2-post")
            return r

    chain = MiddlewareChain()
    chain.use(M1())
    chain.use(M2())
    ctx = RequestContext(method="test", params={})
    await chain.execute(ctx, dummy_handler)
    assert order == ["M1-pre", "M2-pre", "M2-post", "M1-post"], f"顺序错误: {order}"
test("洋葱模型顺序", test_chain_order)

async def test_chain_exception_propagation():
    """中间件抛异常应上浮，后续不执行"""
    class FailMiddleware:
        async def __call__(self, ctx, next_h):
            raise ValueError("blocked!")

    chain = MiddlewareChain()
    chain.use(FailMiddleware())
    chain.use(AddHeaderMiddleware())
    ctx = RequestContext(method="test", params={})
    try:
        await chain.execute(ctx, dummy_handler)
        assert False, "应该抛异常"
    except ValueError as e:
        assert "blocked" in str(e)
test("异常上浮", test_chain_exception_propagation)

async def test_chain_short_circuit():
    """中间件不调 next → 短路"""
    class ShortCircuit:
        async def __call__(self, ctx, next_h):
            return {"short": True}

    chain = MiddlewareChain()
    chain.use(ShortCircuit())
    ctx = RequestContext(method="test", params={})
    result = await chain.execute(ctx, dummy_handler)
    assert result == {"short": True}
test("短路请求", test_chain_short_circuit)

def test_chain_repr():
    chain = MiddlewareChain()
    chain.use(AddHeaderMiddleware())
    chain.use(MultiplyMiddleware())
    r = repr(chain)
    assert "AddHeaderMiddleware" in r
    assert "MultiplyMiddleware" in r
    assert len(chain) == 2
test("repr 和 len", test_chain_repr)


# ═══════════════════════════════════════════
#  validation.py 测试
# ═══════════════════════════════════════════
print("\n=== middleware/validation.py ===")

from src.middleware.validation import ValidationMiddleware, get_method_schema, get_registered_methods
from src.core.errors import InvalidParameterError

async def test_validation_required_missing():
    v = ValidationMiddleware()
    ctx = RequestContext(method="read_file", params={})
    try:
        await v(ctx, dummy_handler)
        assert False
    except InvalidParameterError as e:
        assert "path" in e.message
test("必选参数缺失", test_validation_required_missing)

async def test_validation_type_coerce_int():
    v = ValidationMiddleware()
    ctx = RequestContext(method="replace_range", params={
        "path": "/test/file.txt",
        "start_line": "5",    # str → int
        "end_line": "10",
        "new_text": "hello",
    })
    await v(ctx, dummy_handler)
    assert ctx.params["start_line"] == 5
    assert ctx.params["end_line"] == 10
    assert isinstance(ctx.params["start_line"], int)
test("类型强转 str→int", test_validation_type_coerce_int)

async def test_validation_type_coerce_bool():
    v = ValidationMiddleware()
    ctx = RequestContext(method="create_file", params={
        "path": "/test/f.txt",
        "overwrite": "true",  # str → bool
    })
    await v(ctx, dummy_handler)
    assert ctx.params["overwrite"] is True
test("类型强转 str→bool", test_validation_type_coerce_bool)

async def test_validation_min_value():
    v = ValidationMiddleware()
    ctx = RequestContext(method="replace_range", params={
        "path": "/test/file.txt",
        "start_line": 0,     # min=1
        "end_line": 5,
        "new_text": "x",
    })
    try:
        await v(ctx, dummy_handler)
        assert False
    except InvalidParameterError as e:
        assert "start_line" in e.message
        assert "过小" in e.message
test("数值范围下限", test_validation_min_value)

async def test_validation_non_empty_string():
    v = ValidationMiddleware()
    ctx = RequestContext(method="read_file", params={"path": "  "})
    try:
        await v(ctx, dummy_handler)
        assert False
    except InvalidParameterError as e:
        assert "空字符串" in e.message
test("非空字符串", test_validation_non_empty_string)

async def test_validation_defaults_filled():
    v = ValidationMiddleware()
    ctx = RequestContext(method="create_file", params={
        "path": "/test/f.txt",
    })
    await v(ctx, dummy_handler)
    assert ctx.params["encoding"] == "utf-8"
    assert ctx.params["overwrite"] is False
test("默认值填充", test_validation_defaults_filled)

async def test_validation_unknown_method():
    """未注册方法应透传"""
    v = ValidationMiddleware()
    ctx = RequestContext(method="unknown_method_xyz", params={"any": "thing"})
    result = await v(ctx, dummy_handler)
    assert result["status"] == "ok"
test("未注册方法透传", test_validation_unknown_method)

async def test_validation_tuple_coerce():
    v = ValidationMiddleware()
    ctx = RequestContext(method="read_file", params={
        "path": "/test/f.txt",
        "line_range": [1, 10],
    })
    await v(ctx, dummy_handler)
    assert ctx.params["line_range"] == (1, 10)
    assert isinstance(ctx.params["line_range"], tuple)
test("tuple[int,int] 转换", test_validation_tuple_coerce)

async def test_validation_tuple_bad_length():
    v = ValidationMiddleware()
    ctx = RequestContext(method="read_file", params={
        "path": "/test/f.txt",
        "line_range": [1, 2, 3],
    })
    try:
        await v(ctx, dummy_handler)
        assert False
    except InvalidParameterError as e:
        assert "2 个元素" in e.message
test("tuple 长度不对", test_validation_tuple_bad_length)

async def test_validation_nullable():
    v = ValidationMiddleware()
    ctx = RequestContext(method="read_file", params={
        "path": "/test/f.txt",
        "encoding": None,  # str|None → 允许 None
    })
    await v(ctx, dummy_handler)
    assert ctx.params["encoding"] is None
test("nullable 参数接受 None", test_validation_nullable)

async def test_validation_strict_unknown():
    v = ValidationMiddleware(strict=True)
    ctx = RequestContext(method="ping", params={"bogus": 1})
    try:
        await v(ctx, dummy_handler)
        assert False
    except InvalidParameterError as e:
        assert "bogus" in e.message
test("严格模式拒绝未知参数", test_validation_strict_unknown)

def test_get_registered_methods():
    methods = get_registered_methods()
    assert "read_file" in methods
    assert "run_command" in methods
    assert "ping" in methods
    assert len(methods) > 30
test("get_registered_methods", test_get_registered_methods)

def test_get_method_schema():
    schema = get_method_schema("read_file")
    assert schema is not None
    names = [p.name for p in schema]
    assert "path" in names
    assert "encoding" in names
    assert get_method_schema("nonexistent") is None
test("get_method_schema", test_get_method_schema)


# ═══════════════════════════════════════════
#  audit.py 测试
# ═══════════════════════════════════════════
print("\n=== middleware/audit.py ===")

from src.middleware.audit import AuditMiddleware

async def test_audit_success():
    audit = AuditMiddleware(slow_threshold_ms=10000)
    ctx = RequestContext(method="read_file", params={})
    result = await audit(ctx, dummy_handler)
    assert result["status"] == "ok"
    # 不应有慢操作警告
    assert len(ctx.warnings) == 0
test("审计: 正常请求", test_audit_success)

async def test_audit_slow_warning():
    audit = AuditMiddleware(slow_threshold_ms=1)  # 1ms 阈值
    async def slow_handler(ctx):
        import asyncio
        await asyncio.sleep(0.01)  # 10ms
        return {"status": "ok"}
    ctx = RequestContext(method="read_file", params={})
    await audit(ctx, slow_handler)
    slow_warnings = [w for w in ctx.warnings if w.code == "SLOW_OPERATION"]
    assert len(slow_warnings) == 1
    assert "阈值" in slow_warnings[0].message
test("审计: 慢操作警告", test_audit_slow_warning)

async def test_audit_error_propagation():
    audit = AuditMiddleware()
    async def error_handler(ctx):
        raise InvalidParameterError("test error")
    ctx = RequestContext(method="test", params={})
    try:
        await audit(ctx, error_handler)
        assert False
    except InvalidParameterError:
        pass  # 异常应上浮
test("审计: 异常不吞没", test_audit_error_propagation)


# ═══════════════════════════════════════════
#  rate_limit.py 测试
# ═══════════════════════════════════════════
print("\n=== middleware/rate_limit.py ===")

from src.middleware.rate_limit import RateLimitMiddleware
from src.core.errors import RateLimitError

async def test_rate_limit_allows():
    rl = RateLimitMiddleware(global_rpm=100, read_rpm=50, write_rpm=10)
    ctx = RequestContext(method="read_file", params={})
    result = await rl(ctx, dummy_handler)
    assert result["status"] == "ok"
test("限流: 正常请求通过", test_rate_limit_allows)

async def test_rate_limit_disabled():
    rl = RateLimitMiddleware(global_rpm=1, enabled=False)
    # 即使 rpm=1，禁用后应该总是通过
    for _ in range(5):
        ctx = RequestContext(method="read_file", params={})
        await rl(ctx, dummy_handler)
test("限流: 禁用时透传", test_rate_limit_disabled)

async def test_rate_limit_blocks():
    rl = RateLimitMiddleware(global_rpm=2, read_rpm=2, write_rpm=2, window_ms=60000)
    # 前2次应该通过
    for _ in range(2):
        ctx = RequestContext(method="read_file", params={})
        await rl(ctx, dummy_handler)
    # 第3次应该被限流
    ctx = RequestContext(method="read_file", params={})
    try:
        await rl(ctx, dummy_handler)
        assert False, "应该被限流"
    except RateLimitError as e:
        assert "频繁" in e.message
test("限流: 超限阻断", test_rate_limit_blocks)

async def test_rate_limit_reset():
    rl = RateLimitMiddleware(global_rpm=1, read_rpm=1, write_rpm=1)
    ctx = RequestContext(method="read_file", params={})
    await rl(ctx, dummy_handler)
    rl.reset()
    # reset 后应该能再次通过
    ctx2 = RequestContext(method="read_file", params={})
    await rl(ctx2, dummy_handler)
test("限流: reset 重置", test_rate_limit_reset)


# ═══════════════════════════════════════════
#  security.py 测试
# ═══════════════════════════════════════════
print("\n=== middleware/security.py ===")

import tempfile, os
from pathlib import Path
from src.middleware.security import SecurityMiddleware
from src.core.config import MCPConfig
from src.core.security import SecurityChecker
from src.core.errors import PathOutsideWorkspaceError, BlockedCommandError

async def test_security_validates_path():
    """路径校验: workspace 内的路径应通过"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = MCPConfig(workspace={"root_path": tmpdir})
        sec = SecurityChecker(config.security)
        mw = SecurityMiddleware(config, sec)

        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("hi")

        ctx = RequestContext(method="read_file", params={"path": str(test_file)})
        await mw(ctx, dummy_handler)

        assert "path" in ctx.validated_paths
        assert ctx.validated_paths["path"] == test_file.resolve()
test("安全: 路径校验通过", test_security_validates_path)

async def test_security_rejects_outside_path():
    """路径校验: workspace 外的路径应拒绝"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = MCPConfig(workspace={"root_path": tmpdir})
        sec = SecurityChecker(config.security)
        mw = SecurityMiddleware(config, sec)

        ctx = RequestContext(method="read_file", params={"path": "/etc/passwd"})
        try:
            await mw(ctx, dummy_handler)
            assert False
        except PathOutsideWorkspaceError:
            pass
test("安全: 拒绝workspace外路径", test_security_rejects_outside_path)

async def test_security_validates_command():
    """命令校验: 合法命令应通过"""
    config = MCPConfig()
    sec = SecurityChecker(config.security)
    mw = SecurityMiddleware(config, sec)
    ctx = RequestContext(method="run_command", params={"command": "echo hello"})
    await mw(ctx, dummy_handler)
test("安全: 命令校验通过", test_security_validates_command)

async def test_security_validates_env():
    """env 校验: 安全变量通过，危险变量拒绝"""
    config = MCPConfig()
    sec = SecurityChecker(config.security)
    mw = SecurityMiddleware(config, sec)

    # 安全 env
    ctx = RequestContext(method="run_command", params={
        "command": "echo hi", "env": {"MY_VAR": "ok"}
    })
    await mw(ctx, dummy_handler)

    # 危险 env
    ctx2 = RequestContext(method="run_command", params={
        "command": "echo hi", "env": {"LD_PRELOAD": "/evil.so"}
    })
    try:
        await mw(ctx2, dummy_handler)
        assert False
    except InvalidParameterError:
        pass
test("安全: env校验", test_security_validates_env)


# ═══════════════════════════════════════════
#  集成: 完整链路测试
# ═══════════════════════════════════════════
print("\n=== 集成: build_default_chain ===")

from src.middleware import build_default_chain

async def test_full_chain():
    """完整中间件链: Security → Validation → RateLimit → Handler → Audit"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = MCPConfig(workspace={"root_path": tmpdir})
        sec = SecurityChecker(config.security)
        chain = build_default_chain(
            config, sec,
            rate_limit_enabled=False,
            slow_threshold_ms=10000,
        )

        # 准备文件
        test_file = Path(tmpdir) / "hello.txt"
        test_file.write_text("content")

        ctx = RequestContext(method="read_file", params={
            "path": str(test_file),
        })

        async def mock_read_file(ctx):
            return {"status": "ok", "content": "content"}

        result = await chain.execute(ctx, mock_read_file)
        assert result["status"] == "ok"
        assert "path" in ctx.validated_paths
test("完整链路: read_file", test_full_chain)

async def test_full_chain_validation_fails():
    """完整链路: 参数校验失败应正确阻断"""
    config = MCPConfig()
    sec = SecurityChecker(config.security)
    chain = build_default_chain(config, sec, rate_limit_enabled=False)

    ctx = RequestContext(method="read_file", params={})  # 缺少 path
    try:
        await chain.execute(ctx, dummy_handler)
        assert False
    except InvalidParameterError as e:
        assert "path" in e.message
test("完整链路: 参数校验阻断", test_full_chain_validation_fails)

async def test_full_chain_repr():
    config = MCPConfig()
    sec = SecurityChecker(config.security)
    chain = build_default_chain(config, sec)
    r = repr(chain)
    assert "SecurityMiddleware" in r
    assert "ValidationMiddleware" in r
    assert "RateLimitMiddleware" in r
    assert "AuditMiddleware" in r
    assert len(chain) == 4
test("完整链路: repr", test_full_chain_repr)


# ═══════════════════════════════════════════
#  RequestContext.duration_ms 测试
# ═══════════════════════════════════════════
print("\n=== RequestContext.duration_ms ===")

def test_duration_ms():
    ctx = RequestContext(method="test", params={})
    time.sleep(0.01)
    d = ctx.duration_ms
    assert d >= 5, f"耗时太短: {d}ms"
    assert d < 1000, f"耗时太长: {d}ms"
test("duration_ms 计时", test_duration_ms)


# ═══════════════════════════════════════════
#  RateLimitError 测试
# ═══════════════════════════════════════════
print("\n=== core/errors.py RateLimitError ===")

def test_rate_limit_error_structure():
    e = RateLimitError("too fast", details={"method": "read_file"})
    d = e.to_dict()
    assert d["code"] == "RATE_LIMIT_EXCEEDED"
    assert d["message"] == "too fast"
    assert e.http_status == 429
test("RateLimitError 结构", test_rate_limit_error_structure)


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
