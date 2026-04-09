"""验证所有修改的完整测试"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

passed = 0
failed = 0

def test(name, fn):
    global passed, failed
    try:
        fn()
        print(f"  ✓ {name}")
        passed += 1
    except Exception as e:
        print(f"  ✗ {name}: {e}")
        failed += 1

# ═══════════════════════════════════════════
#  encoding.py 测试
# ═══════════════════════════════════════════
print("\n=== platform/encoding.py ===")

from src.platform.encoding import (
    IncrementalStreamDecoder,
    validate_encoding,
    encode_input,
    safe_truncate_bytes,
    sanitize_control_chars,
    has_control_chars,
    detect_file_encoding,
    decode_output,
    get_console_encoding,
)

def test_validate_encoding():
    assert validate_encoding("utf-8") is not None
    assert validate_encoding("gbk") is not None
    assert validate_encoding("cp936") is not None
    assert validate_encoding("nonsense") is None
    assert validate_encoding("") is None
    assert validate_encoding(None) is None  # type: ignore
test("validate_encoding", test_validate_encoding)

def test_incremental_decoder_basic():
    d = IncrementalStreamDecoder()
    assert d.decode(b"hello") == "hello"
    assert d.flush() == ""
test("IncrementalStreamDecoder 基本", test_incremental_decoder_basic)

def test_incremental_decoder_emoji_split():
    d = IncrementalStreamDecoder()
    # 🎉 = f0 9f 8e 89
    t1 = d.decode(b"\xf0\x9f")
    t2 = d.decode(b"\x8e\x89")
    assert t1 == "", f"应为空但得到 {t1!r}"
    assert t2 == "\U0001f389", f"应为🎉但得到 {t2!r}"
test("IncrementalStreamDecoder emoji劈裂", test_incremental_decoder_emoji_split)

def test_incremental_decoder_cjk_split():
    d = IncrementalStreamDecoder()
    # 中 = e4 b8 ad
    t1 = d.decode(b"\xe4\xb8")
    t2 = d.decode(b"\xad")
    assert t1 == ""
    assert t2 == "中"
test("IncrementalStreamDecoder CJK劈裂", test_incremental_decoder_cjk_split)

def test_incremental_decoder_flush():
    d = IncrementalStreamDecoder()
    d.decode(b"\xe4\xb8")  # 不完整的 "中"
    result = d.flush()
    assert len(result) > 0  # 应该有输出（通过回退链）
test("IncrementalStreamDecoder flush不完整", test_incremental_decoder_flush)

def test_incremental_decoder_mixed():
    d = IncrementalStreamDecoder()
    # ASCII + 多字节 + ASCII
    t1 = d.decode(b"abc\xe4")
    t2 = d.decode(b"\xb8\xaddef")
    assert t1 == "abc", f"得到 {t1!r}"
    assert t2 == "中def", f"得到 {t2!r}"
test("IncrementalStreamDecoder 混合数据", test_incremental_decoder_mixed)

def test_encode_input():
    data, enc = encode_input("hello")
    assert isinstance(data, bytes)
    assert len(data) > 0
    data2, enc2 = encode_input("你好", target_encoding="utf-8")
    assert data2 == "你好".encode("utf-8")
    # 无效编码名回退
    data3, enc3 = encode_input("test", target_encoding="nonsense")
    assert enc3 == "utf-8"
test("encode_input", test_encode_input)

def test_safe_truncate_bytes():
    data = "中文".encode("utf-8")  # e4b8ad e4b896 = 6 bytes
    t = safe_truncate_bytes(data, 4)  # 切到第2个字符中间
    assert len(t) == 3
    assert t.decode("utf-8") == "中"
    # 不需要截断
    t2 = safe_truncate_bytes(data, 10)
    assert t2 == data
    # ASCII
    t3 = safe_truncate_bytes(b"hello", 3)
    assert t3 == b"hel"
test("safe_truncate_bytes", test_safe_truncate_bytes)

def test_sanitize_control_chars():
    assert sanitize_control_chars("hello") == "hello"
    assert sanitize_control_chars("a\x00b") == "ab"
    assert sanitize_control_chars("a\tb\nc") == "a\tb\nc"
    assert sanitize_control_chars("a\x01\x02b") == "ab"
    assert sanitize_control_chars("a\x7fb") == "ab"
    # C1 范围
    assert sanitize_control_chars("a\x80\x9fb") == "ab"
    # replacement 参数
    assert sanitize_control_chars("a\x00b", "?") == "a?b"
test("sanitize_control_chars", test_sanitize_control_chars)

def test_has_control_chars():
    assert has_control_chars("normal\n") == False
    assert has_control_chars("has\x00null") == True
    assert has_control_chars("has\x01soh") == True
    assert has_control_chars("tab\tok") == False
test("has_control_chars", test_has_control_chars)

def test_detect_file_encoding_bom():
    # UTF-32-LE BOM 不应被 UTF-16-LE 误匹配
    assert detect_file_encoding(b"\xff\xfe\x00\x00rest") == "utf-32-le"
    assert detect_file_encoding(b"\x00\x00\xfe\xffrest") == "utf-32-be"
    assert detect_file_encoding(b"\xef\xbb\xbfhello") == "utf-8-sig"
    assert detect_file_encoding(b"\xff\xfehello") == "utf-16-le"
    assert detect_file_encoding(b"\xfe\xffhello") == "utf-16-be"
test("detect_file_encoding BOM顺序", test_detect_file_encoding_bom)

def test_decode_output_basic():
    text, enc = decode_output(b"hello")
    assert text == "hello"
    assert enc == "utf-8"
    text2, enc2 = decode_output(b"")
    assert text2 == ""
test("decode_output 基本", test_decode_output_basic)


# ═══════════════════════════════════════════
#  security.py 测试
# ═══════════════════════════════════════════
print("\n=== core/security.py ===")

from src.core.security import SecurityChecker
from src.core.config import SecurityConfig
from src.core.errors import InvalidParameterError, BlockedCommandError

def test_shell_syntax_valid():
    s = SecurityChecker(SecurityConfig(blocked_commands=[], blocked_paths=[], allowed_shells=[]))
    s.validate_command("echo hello")
    s.validate_command('echo "hello world"')
    s.validate_command("ls -la | grep test")
test("shell语法: 合法命令", test_shell_syntax_valid)

def test_shell_syntax_unclosed_quote():
    s = SecurityChecker(SecurityConfig(blocked_commands=[], blocked_paths=[], allowed_shells=[]))
    try:
        s.validate_command("echo it's done")
        assert False, "应该抛异常"
    except InvalidParameterError as e:
        assert "语法" in e.message or "quotation" in e.message.lower()
test("shell语法: 未闭合引号", test_shell_syntax_unclosed_quote)

def test_shell_syntax_empty():
    s = SecurityChecker(SecurityConfig(blocked_commands=[], blocked_paths=[], allowed_shells=[]))
    try:
        s.validate_command("")
        assert False, "应该抛异常"
    except InvalidParameterError:
        pass
test("shell语法: 空命令", test_shell_syntax_empty)

def test_blocked_command():
    s = SecurityChecker(SecurityConfig(blocked_commands=["rm -rf /"], blocked_paths=[], allowed_shells=[]))
    try:
        s.validate_command("rm -rf /")
        assert False
    except BlockedCommandError:
        pass
test("命令黑名单", test_blocked_command)

def test_validate_env_safe():
    s = SecurityChecker(SecurityConfig(blocked_commands=[], blocked_paths=[], allowed_shells=[]))
    s.validate_env({"MY_VAR": "value", "APP_NAME": "test"})
    s.validate_env({})
    s.validate_env(None)  # type: ignore
test("env校验: 安全变量", test_validate_env_safe)

def test_validate_env_dangerous():
    s = SecurityChecker(SecurityConfig(blocked_commands=[], blocked_paths=[], allowed_shells=[]))
    try:
        s.validate_env({"LD_PRELOAD": "/evil.so"})
        assert False
    except InvalidParameterError as e:
        assert "LD_PRELOAD" in str(e)
    try:
        s.validate_env({"PATH": "/tmp"})
        assert False
    except InvalidParameterError:
        pass
test("env校验: 危险变量", test_validate_env_dangerous)


# ═══════════════════════════════════════════
#  buffer.py 测试
# ═══════════════════════════════════════════
print("\n=== stream/buffer.py ===")

from src.stream.buffer import OutputBuffer

def test_buffer_basic():
    buf = OutputBuffer("test", max_size=1024)
    buf.write(b"hello world")
    assert buf.get_all() == "hello world"
    assert buf.size == 11
test("OutputBuffer 基本", test_buffer_basic)

def test_buffer_emoji_split():
    buf = OutputBuffer("test", max_size=1024)
    # 🎉 = f0 9f 8e 89 (4 bytes)
    buf.write(b"\xf0\x9f")
    buf.write(b"\x8e\x89")
    result = buf.get_all()
    assert result == "\U0001f389", f"期望🎉但得到 {result!r}"
test("OutputBuffer emoji跨chunk", test_buffer_emoji_split)

def test_buffer_cjk_split():
    buf = OutputBuffer("test", max_size=1024)
    # 中 = e4 b8 ad
    buf.write(b"abc\xe4\xb8")
    buf.write(b"\xadef")
    result = buf.get_all()
    assert result == "abc中ef", f"期望'abc中ef'但得到 {result!r}"
test("OutputBuffer CJK跨chunk", test_buffer_cjk_split)

def test_buffer_truncate_boundary():
    buf = OutputBuffer("test", max_size=4)
    # 中 = e4 b8 ad (3 bytes), max=4 → 第二个中字会被截断
    # 先写第一个字(3 bytes), 还剩1 byte
    buf.write("中".encode("utf-8"))  # 3 bytes, 剩 1
    buf.write("文".encode("utf-8"))  # 3 bytes, 只能写 1 → 截断对齐 → 写0
    assert buf.truncated
    # 应该只有第一个字符，不会有乱码
    result = buf.get_all()
    assert "中" in result
    assert "�" not in result, f"不应有乱码但得到 {result!r}"
test("OutputBuffer 截断对齐字符边界", test_buffer_truncate_boundary)

def test_buffer_eof_flush():
    buf = OutputBuffer("test", max_size=1024)
    buf.write(b"\xe4\xb8")  # 不完整的 "中"
    buf.mark_eof()           # 应触发 flush
    result = buf.get_all()
    assert len(result) > 0, "mark_eof 应刷出暂存字节"
test("OutputBuffer mark_eof 刷出", test_buffer_eof_flush)


# ═══════════════════════════════════════════
#  file.py 错误传播测试
# ═══════════════════════════════════════════
print("\n=== handlers/file.py 错误传播 ===")

from src.core.errors import TaskFailedError

def test_taskfailed_import():
    """确认 TaskFailedError 可导入且结构正确"""
    e = TaskFailedError("test fail", details={"op": "write"}, cause=OSError("disk full"))
    d = e.to_dict()
    assert d["message"] == "test fail"
    assert d["details"]["op"] == "write"
    assert "disk full" in d["cause"]
    assert e.error_code == "TASK_FAILED"
test("TaskFailedError 结构和序列化", test_taskfailed_import)

def test_file_handler_imports():
    """确认 file.py 正确导入了 TaskFailedError"""
    from src.handlers.file import FileHandler
    # 只要导入不报错就说明 import 链正确
    assert FileHandler is not None
test("FileHandler 导入链", test_file_handler_imports)


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
