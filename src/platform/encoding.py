"""
Layer 2: Platform — 编码处理

统一的编码边界层。所有 OS 边界处的编码/解码操作必须经过此模块。

职责:
1. 编码名校验: validate_encoding()
2. 进程输出解码 (bytes → str): decode_output(), IncrementalStreamDecoder
3. 进程输入编码 (str → bytes): encode_input()
4. 文件编码检测: detect_file_encoding()
5. 字节截断保护: safe_truncate_bytes()
6. 控制字符清洗: sanitize_control_chars(), has_control_chars()

其他层禁止直接用 .encode("utf-8") 或 .decode("utf-8") 跨 OS 边界，
统一走这里。
"""

from __future__ import annotations

import codecs
import locale
import sys

IS_WINDOWS = sys.platform == "win32"

# 缓存控制台编码，避免重复调用
_console_encoding_cache: str | None = None


# ═══════════════════════════════════════════════════════
#  编码名校验
# ═══════════════════════════════════════════════════════

def validate_encoding(name: str) -> str | None:
    """
    校验编码名是否为 Python 支持的编码

    Args:
        name: 编码名（如 "utf-8", "gbk", "cp936"）

    Returns:
        标准化编码名（如 "utf-8" → "utf-8"），
        无效时返回 None
    """
    if not name or not isinstance(name, str):
        return None
    try:
        info = codecs.lookup(name)
        return info.name
    except LookupError:
        return None


# ═══════════════════════════════════════════════════════
#  控制台编码
# ═══════════════════════════════════════════════════════

def get_console_encoding() -> str:
    """
    获取系统控制台的默认编码

    Windows 中文环境通常是 cp936 (GBK)，
    其他语言环境可能是 cp1252 (西欧)、cp932 (日文) 等。
    Linux/macOS 一律返回 utf-8。

    Returns:
        编码名称字符串，如 "cp936", "utf-8"
    """
    global _console_encoding_cache
    if _console_encoding_cache is not None:
        return _console_encoding_cache

    if IS_WINDOWS:
        # 方法 1: 通过 Windows API 获取控制台代码页
        try:
            import ctypes
            cp = ctypes.windll.kernel32.GetConsoleOutputCP()
            if cp > 0:
                candidate = f"cp{cp}"
                if validate_encoding(candidate):
                    _console_encoding_cache = candidate
                    return _console_encoding_cache
        except (AttributeError, OSError, ValueError):
            pass

        # 方法 2: 系统首选编码
        preferred = locale.getpreferredencoding(False)
        if preferred and validate_encoding(preferred):
            _console_encoding_cache = preferred
            return _console_encoding_cache

        # 方法 3: 兜底 — 使用系统 ANSI 代码页
        # 'mbcs' 是 Windows 特有编码，自动映射到系统代码页
        # (中文=cp936, 日文=cp932, 韩文=cp949, 西欧=cp1252 等)
        _console_encoding_cache = "mbcs"
        return _console_encoding_cache

    _console_encoding_cache = "utf-8"
    return _console_encoding_cache


def reset_console_encoding_cache() -> None:
    """重置控制台编码缓存（仅用于测试）"""
    global _console_encoding_cache
    _console_encoding_cache = None


def decode_output(data: bytes) -> tuple[str, str]:
    """
    智能解码命令输出

    使用多编码回退链，尽可能无损地将字节转为字符串。

    回退顺序:
    1. UTF-8（最通用，Linux 默认）
    2. 系统控制台编码（Windows: cpXXX）
    3. GBK（中文环境兜底）
    4. UTF-8 errors='replace'（最终兜底，用 � 替换无法解码的字节）

    Args:
        data: 原始字节数据

    Returns:
        (decoded_text, encoding_used)
        - decoded_text: 解码后的字符串
        - encoding_used: 实际使用的编码名称
    """
    if not data:
        return ("", "utf-8")

    # 尝试 1: UTF-8（最优先，跨平台通用）
    try:
        return (data.decode("utf-8"), "utf-8")
    except UnicodeDecodeError:
        pass

    # 尝试 2: 系统控制台编码
    console_enc = get_console_encoding()
    if console_enc.lower() not in ("utf-8", "utf8"):
        try:
            return (data.decode(console_enc), console_enc)
        except (UnicodeDecodeError, LookupError):
            pass

    # 尝试 3: locale 编码（可能和控制台编码不同）
    try:
        locale_enc = locale.getpreferredencoding(False)
        if locale_enc and locale_enc.lower() not in ("utf-8", "utf8", console_enc.lower()):
            try:
                return (data.decode(locale_enc), locale_enc)
            except (UnicodeDecodeError, LookupError):
                pass
    except (ValueError, AttributeError):
        pass

    # 尝试 4: 最终兜底，用 ▯ 替换无法解码的字节
    return (data.decode("utf-8", errors="replace"), "utf-8-replace")


def detect_file_encoding(data: bytes, default: str = "utf-8") -> str:
    """
    检测文件内容编码

    简单启发式，不依赖外部库:
    1. 有 BOM → 对应编码
    2. 尝试 UTF-8
    3. 尝试系统编码
    4. 尝试 GBK
    5. 回退到 default

    Args:
        data: 文件头部字节（建议至少 8KB）
        default: 检测失败时的默认编码

    Returns:
        检测到的编码名称
    """
    if not data:
        return default

    # BOM 检测 — 长 BOM 优先，避免 UTF-32-LE 被 UTF-16-LE 误匹配
    if data[:4] == b"\xff\xfe\x00\x00":
        return "utf-32-le"
    if data[:4] == b"\x00\x00\xfe\xff":
        return "utf-32-be"
    if data[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig"
    if data[:2] == b"\xff\xfe":
        return "utf-16-le"
    if data[:2] == b"\xfe\xff":
        return "utf-16-be"

    # 尝试 UTF-8
    try:
        data.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass

    # 尝试系统控制台编码
    console_enc = get_console_encoding()
    if console_enc.lower() not in ("utf-8", "utf8"):
        try:
            data.decode(console_enc)
            return console_enc
        except (UnicodeDecodeError, LookupError):
            pass

    # 尝试 locale 编码
    try:
        locale_enc = locale.getpreferredencoding(False)
        if locale_enc and locale_enc.lower() not in ("utf-8", "utf8", console_enc.lower()):
            try:
                data.decode(locale_enc)
                return locale_enc
            except (UnicodeDecodeError, LookupError):
                pass
    except (ValueError, AttributeError):
        pass

    return default


def safe_encode(text: str, encoding: str = "utf-8", errors: str = "replace") -> bytes:
    """
    安全编码字符串为字节，不会抛异常

    如果目标编码失败，回退到 UTF-8 errors='replace'。

    Args:
        text: 要编码的字符串
        encoding: 目标编码
        errors: 错误处理策略

    Returns:
        编码后的字节
    """
    try:
        return text.encode(encoding, errors=errors)
    except (UnicodeEncodeError, LookupError):
        return text.encode("utf-8", errors="replace")


# ═══════════════════════════════════════════════════════
#  进程输入编码
# ═══════════════════════════════════════════════════════

def encode_input(text: str, target_encoding: str | None = None) -> tuple[bytes, str]:
    """
    将字符串编码为目标进程期望的字节序列

    编码选择:
    1. 明确指定 target_encoding → 使用它
    2. Windows → 控制台编码 (cpXXX)
    3. 其他 → UTF-8

    如果目标编码无法表示某些字符，自动回退到 UTF-8，不抛异常。

    Args:
        text: 要编码的字符串
        target_encoding: 目标编码，None 则自动选择

    Returns:
        (encoded_bytes, encoding_used)
    """
    if not text:
        return (b"", target_encoding or "utf-8")

    # 明确指定编码
    if target_encoding:
        normalized = validate_encoding(target_encoding)
        if normalized is None:
            # 无效编码名，回退到 UTF-8
            return (text.encode("utf-8"), "utf-8")
        try:
            return (text.encode(normalized), normalized)
        except UnicodeEncodeError:
            return (text.encode("utf-8"), "utf-8")

    # 自动选择
    if IS_WINDOWS:
        enc = get_console_encoding()
        try:
            return (text.encode(enc), enc)
        except (UnicodeEncodeError, LookupError):
            pass

    return (text.encode("utf-8"), "utf-8")


# ═══════════════════════════════════════════════════════
#  流式增量解码器
# ═══════════════════════════════════════════════════════

class IncrementalStreamDecoder:
    """
    流式增量解码器

    解决 pipe 分块导致多字节字符跨 chunk 劈裂的问题。

    原理:
    - 每次收到新的字节块，追加到内部暂存区
    - 尝试 UTF-8 解码，保留尾部可能不完整的字节
    - 如果检测到数据不是 UTF-8（错误位置不在尾部），自动切换到平台编码
    - 流结束时强制解码全部剩余字节（走完整回退链）

    用法::

        decoder = IncrementalStreamDecoder()
        text1 = decoder.decode(chunk1)
        text2 = decoder.decode(chunk2)
        text3 = decoder.flush()  # 流结束时
    """

    def __init__(self) -> None:
        self._pending: bytearray = bytearray()
        self._encoding_used: str = "utf-8"
        self._is_utf8: bool = True

    def decode(self, data: bytes, final: bool = False) -> str:
        """
        解码一块字节数据

        Args:
            data: 新收到的字节
            final: 是否为最后一块（流结束）

        Returns:
            解码后的字符串。可能为空（数据被暂存等下一块补全）。
        """
        if not data and not final:
            return ""

        if data:
            self._pending.extend(data)

        if not self._pending:
            return ""

        if final:
            return self._decode_final()

        if self._is_utf8:
            return self._decode_utf8_incremental()
        else:
            return self._decode_fallback_incremental()

    def flush(self) -> str:
        """
        流结束时调用，解码所有暂存的字节

        等价于 decode(b"", final=True)。
        """
        return self.decode(b"", final=True)

    def reset(self) -> None:
        """重置解码器状态"""
        self._pending.clear()
        self._encoding_used = "utf-8"
        self._is_utf8 = True

    @property
    def encoding_used(self) -> str:
        """最后一次解码使用的编码"""
        return self._encoding_used

    @property
    def pending_bytes(self) -> int:
        """当前暂存的未解码字节数"""
        return len(self._pending)

    # ── 内部方法 ──

    def _decode_utf8_incremental(self) -> str:
        """UTF-8 增量解码，保留尾部不完整字节"""
        buf = bytes(self._pending)

        # 计算尾部可能不完整的字节数
        tail_incomplete = _utf8_incomplete_tail_length(buf)

        if tail_incomplete >= len(buf):
            # 全部都是不完整序列的一部分，等更多数据
            return ""

        if tail_incomplete > 0:
            to_decode = buf[:-tail_incomplete]
        else:
            to_decode = buf

        try:
            text = to_decode.decode("utf-8")
            if tail_incomplete > 0:
                self._pending = bytearray(buf[-tail_incomplete:])
            else:
                self._pending.clear()
            self._encoding_used = "utf-8"
            return text
        except UnicodeDecodeError:
            # 不是 UTF-8 数据，切换到回退编码
            self._is_utf8 = False
            return self._decode_fallback_incremental()

    def _decode_fallback_incremental(self) -> str:
        """非 UTF-8 回退编码解码"""
        buf = bytes(self._pending)

        # 尝试控制台编码
        console_enc = get_console_encoding()
        if console_enc.lower() not in ("utf-8", "utf8"):
            try:
                text = buf.decode(console_enc)
                self._pending.clear()
                self._encoding_used = console_enc
                return text
            except (UnicodeDecodeError, LookupError):
                pass

        # 尝试 locale 编码
        try:
            locale_enc = locale.getpreferredencoding(False)
            if locale_enc and locale_enc.lower() not in ("utf-8", "utf8"):
                try:
                    text = buf.decode(locale_enc)
                    self._pending.clear()
                    self._encoding_used = locale_enc
                    return text
                except (UnicodeDecodeError, LookupError):
                    pass
        except (ValueError, AttributeError):
            pass

        # 最终兜底
        text = buf.decode("utf-8", errors="replace")
        self._pending.clear()
        self._encoding_used = "utf-8-replace"
        return text

    def _decode_final(self) -> str:
        """流结束，解码全部剩余字节"""
        buf = bytes(self._pending)
        self._pending.clear()

        if not buf:
            return ""

        # 复用 decode_output 的完整回退链
        text, enc = decode_output(buf)
        self._encoding_used = enc
        return text


# ═══════════════════════════════════════════════════════
#  字节截断保护
# ═══════════════════════════════════════════════════════

def safe_truncate_bytes(data: bytes, max_bytes: int) -> bytes:
    """
    按字节截断，但对齐到 UTF-8 字符边界

    避免从多字节字符中间切开，确保截断后的字节能完整解码。

    Args:
        data: 原始字节
        max_bytes: 最大字节数

    Returns:
        截断后的字节，长度 <= max_bytes，尾部不含不完整 UTF-8 序列
    """
    if len(data) <= max_bytes:
        return data

    truncated = data[:max_bytes]
    incomplete = _utf8_incomplete_tail_length(truncated)
    if 0 < incomplete <= len(truncated):
        truncated = truncated[:-incomplete]
    return truncated


# ═══════════════════════════════════════════════════════
#  控制字符清洗
# ═══════════════════════════════════════════════════════

# 允许保留的控制字符: 换行(0x0A)、回车(0x0D)、制表(0x09)
_ALLOWED_CONTROL_CHARS = frozenset({0x09, 0x0A, 0x0D})


def sanitize_control_chars(text: str, replacement: str = "") -> str:
    """
    移除/替换不安全的控制字符

    保留 \\t(0x09), \\n(0x0A), \\r(0x0D)。
    移除 NUL(0x00) 和其他 C0/C1 控制字符。

    C0 范围: 0x00-0x1F（排除允许的 0x09/0x0A/0x0D）
    C1 范围: 0x80-0x9F
    DEL: 0x7F

    Args:
        text: 输入文本
        replacement: 替换字符，默认空字符串（直接删除）

    Returns:
        清洗后的文本
    """
    if not text:
        return text

    chars: list[str] = []
    for ch in text:
        cp = ord(ch)
        if cp < 0x20:
            if cp in _ALLOWED_CONTROL_CHARS:
                chars.append(ch)
            else:
                chars.append(replacement)
        elif cp == 0x7F:
            chars.append(replacement)
        elif 0x80 <= cp <= 0x9F:
            chars.append(replacement)
        else:
            chars.append(ch)

    return "".join(chars)


def has_control_chars(text: str) -> bool:
    """
    检查文本是否包含不安全的控制字符

    判断标准与 sanitize_control_chars 一致。

    Args:
        text: 输入文本

    Returns:
        True 包含不安全控制字符
    """
    for ch in text:
        cp = ord(ch)
        if cp < 0x20 and cp not in _ALLOWED_CONTROL_CHARS:
            return True
        if cp == 0x7F:
            return True
        if 0x80 <= cp <= 0x9F:
            return True
    return False


# ═══════════════════════════════════════════════════════
#  内部工具函数
# ═══════════════════════════════════════════════════════

def _utf8_incomplete_tail_length(data: bytes) -> int:
    """
    检查字节序列尾部是否有不完整的 UTF-8 多字节序列

    UTF-8 编码规则:
      0xxxxxxx                          — 1 字节 (ASCII)
      110xxxxx 10xxxxxx                 — 2 字节
      1110xxxx 10xxxxxx 10xxxxxx        — 3 字节
      11110xxx 10xxxxxx 10xxxxxx 10xxxxxx — 4 字节

    从尾部往前扫描（最多 4 字节），如果发现一个多字节序列的
    首字节（0xC0+）但后续续行字节不足，则这些字节不完整。

    Args:
        data: 字节序列

    Returns:
        尾部不完整序列的字节数。0 表示尾部完整。
    """
    if not data:
        return 0

    check_len = min(4, len(data))

    for i in range(1, check_len + 1):
        byte = data[-i]

        if byte < 0x80:
            # ASCII 字节
            if i == 1:
                return 0  # 最后一个字节是 ASCII，整体完整
            else:
                # ASCII 之后有续行字节 → 数据异常
                break

        elif byte >= 0xC0:
            # 多字节序列的首字节
            if byte < 0xE0:
                expected_len = 2
            elif byte < 0xF0:
                expected_len = 3
            elif byte < 0xF8:
                expected_len = 4
            else:
                # 无效 UTF-8 首字节 (0xF8+)
                return 0

            actual_len = i  # 从首字节到 data 末尾的长度
            if actual_len < expected_len:
                return actual_len  # 不完整
            else:
                return 0  # 完整

        # 0x80-0xBF: 续行字节，继续往前扫描

    # 扫描 4 字节全是续行字节 → 数据异常，不认为是不完整序列
    return 0
