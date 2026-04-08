"""
Layer 2: Platform — 编码处理

职责:
- 获取系统控制台默认编码
- 智能解码命令输出（多编码回退链）
- 检测文件编码

其他层禁止直接用 sys.platform 做编码判断，统一走这里。
"""

from __future__ import annotations

import locale
import sys

IS_WINDOWS = sys.platform == "win32"

# 缓存控制台编码，避免重复调用
_console_encoding_cache: str | None = None


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
                _console_encoding_cache = f"cp{cp}"
                return _console_encoding_cache
        except (AttributeError, OSError, ValueError):
            pass

        # 方法 2: 系统首选编码
        preferred = locale.getpreferredencoding(False)
        if preferred:
            _console_encoding_cache = preferred
            return _console_encoding_cache

        # 方法 3: 中文环境兜底
        _console_encoding_cache = "cp936"
        return _console_encoding_cache

    _console_encoding_cache = "utf-8"
    return _console_encoding_cache


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

    # 尝试 2: 系统控制台编码（Windows 环境关键）
    if IS_WINDOWS:
        console_enc = get_console_encoding()
        if console_enc.lower() != "utf-8":
            try:
                return (data.decode(console_enc), console_enc)
            except (UnicodeDecodeError, LookupError):
                pass

    # 尝试 3: GBK（中文环境兜底）
    try:
        return (data.decode("gbk"), "gbk")
    except (UnicodeDecodeError, LookupError):
        pass

    # 尝试 4: Latin-1（不会失败，但可能乱码 — 用于纯二进制检测前的保底）
    # 不使用 latin-1，直接走 replace，让调用方知道有损失
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

    # BOM 检测
    if data[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig"
    if data[:2] == b"\xff\xfe":
        return "utf-16-le"
    if data[:2] == b"\xfe\xff":
        return "utf-16-be"
    if data[:4] == b"\xff\xfe\x00\x00":
        return "utf-32-le"
    if data[:4] == b"\x00\x00\xfe\xff":
        return "utf-32-be"

    # 尝试 UTF-8
    try:
        data.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass

    # 尝试系统编码
    if IS_WINDOWS:
        console_enc = get_console_encoding()
        try:
            data.decode(console_enc)
            return console_enc
        except (UnicodeDecodeError, LookupError):
            pass

    # 尝试 GBK
    try:
        data.decode("gbk")
        return "gbk"
    except (UnicodeDecodeError, LookupError):
        pass

    return default


def safe_encode(text: str, encoding: str = "utf-8") -> bytes:
    """
    安全编码字符串为字节

    如果目标编码失败，回退到 UTF-8。

    Args:
        text: 要编码的字符串
        encoding: 目标编码

    Returns:
        编码后的字节
    """
    try:
        return text.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return text.encode("utf-8", errors="replace")
