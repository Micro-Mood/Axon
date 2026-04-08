"""
Layer 2: Platform — 文件系统差异

职责:
- 判断文件是否隐藏 (Windows: 属性位, Linux: .前缀)
- 获取平台特定文件属性 (hidden, system, archive)
- 清理文件名 (移除平台不允许的字符)
- 路径分隔符规范化

其他层禁止直接用 st_file_attributes 或判断 sys.platform，统一走这里。
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"


# ═══════════════════════════════════════════════════════
#  隐藏文件检测
# ═══════════════════════════════════════════════════════

def is_hidden(path: Path) -> bool:
    """
    判断文件/目录是否为隐藏状态

    Windows: 检查 FILE_ATTRIBUTE_HIDDEN 属性位
    Linux/macOS: 检查文件名是否以 . 开头

    两个平台的检查都会做，满足任一即为隐藏:
    - Windows 上 .gitignore 也算隐藏（名称以.开头）
    - 无法获取属性时只按名称判断

    Args:
        path: 文件或目录路径

    Returns:
        True 为隐藏
    """
    # 名称以 . 开头 → 任何平台都算隐藏
    if path.name.startswith("."):
        return True

    # Windows 属性位检查
    if IS_WINDOWS:
        try:
            attrs = path.stat().st_file_attributes  # type: ignore[attr-defined]
            if attrs & stat.FILE_ATTRIBUTE_HIDDEN:
                return True
        except (AttributeError, OSError):
            pass

    return False


# ═══════════════════════════════════════════════════════
#  文件属性
# ═══════════════════════════════════════════════════════

def get_file_attributes(path: Path) -> dict[str, bool]:
    """
    获取平台特定文件属性

    Windows 返回完整的 hidden/system/archive 信息，
    Linux 只能判断 hidden（通过 .前缀）。

    Args:
        path: 文件路径

    Returns:
        {
            "is_hidden": bool,
            "is_system": bool,   # Linux 始终 False
            "is_archive": bool,  # Linux 始终 False
        }
    """
    result = {
        "is_hidden": False,
        "is_system": False,
        "is_archive": False,
    }

    # 名称检查（跨平台）
    result["is_hidden"] = path.name.startswith(".")

    # Windows 属性位
    if IS_WINDOWS:
        try:
            st = path.stat()
            attrs = st.st_file_attributes  # type: ignore[attr-defined]
            result["is_hidden"] = result["is_hidden"] or bool(
                attrs & stat.FILE_ATTRIBUTE_HIDDEN
            )
            result["is_system"] = bool(attrs & stat.FILE_ATTRIBUTE_SYSTEM)
            result["is_archive"] = bool(attrs & stat.FILE_ATTRIBUTE_ARCHIVE)
        except (AttributeError, OSError):
            pass

    return result


def get_file_attributes_from_stat(
    stat_info: os.stat_result, name: str = ""
) -> dict[str, bool]:
    """
    从已有的 stat_result 提取平台特定属性（避免重复 stat 调用）

    当你已经拿到 stat_info 时用这个，比 get_file_attributes() 更高效。

    Args:
        stat_info: os.stat() 或 Path.stat() 的返回值
        name: 文件名（用于 .前缀 检查），空字符串则跳过

    Returns:
        同 get_file_attributes()
    """
    result = {
        "is_hidden": name.startswith(".") if name else False,
        "is_system": False,
        "is_archive": False,
    }

    if IS_WINDOWS and hasattr(stat_info, "st_file_attributes"):
        attrs = stat_info.st_file_attributes
        result["is_hidden"] = result["is_hidden"] or bool(
            attrs & stat.FILE_ATTRIBUTE_HIDDEN
        )
        result["is_system"] = bool(attrs & stat.FILE_ATTRIBUTE_SYSTEM)
        result["is_archive"] = bool(attrs & stat.FILE_ATTRIBUTE_ARCHIVE)

    return result


# ═══════════════════════════════════════════════════════
#  文件名清理
# ═══════════════════════════════════════════════════════

# Windows 保留设备名（不允许作为文件名）
_WINDOWS_RESERVED_NAMES = frozenset({
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
})

# Windows 禁止的字符: < > : " / \ | ? * 以及控制字符 0x00-0x1F
_WINDOWS_FORBIDDEN_CHARS = frozenset(
    '<>:"/\\|?*' + "".join(chr(i) for i in range(32))
)

# POSIX 禁止的字符: / 和 \0
_POSIX_FORBIDDEN_CHARS = frozenset("/\0")


def sanitize_filename(filename: str) -> str:
    """
    清理文件名，移除当前平台不允许的字符

    Windows:
    - 移除 <>:"/\\|?* 和控制字符 (0x00-0x1F)
    - 移除末尾的 . 和空格
    - 保留名称（CON, PRN, COM1 等）加 _ 前缀

    Linux/macOS:
    - 只移除 / 和 \\0

    所有平台:
    - 空结果返回 "unnamed"
    - 限制最大长度 255 字符

    Args:
        filename: 原始文件名

    Returns:
        清理后的安全文件名
    """
    if not filename:
        return "unnamed"

    if IS_WINDOWS:
        result = filename
        for c in _WINDOWS_FORBIDDEN_CHARS:
            result = result.replace(c, "_")

        # 移除末尾的 . 和空格（Windows 会自动忽略它们，导致歧义）
        result = result.rstrip(". ")

        # 保留名称检查（不区分大小写，不管扩展名）
        stem = Path(result).stem.upper()
        if stem in _WINDOWS_RESERVED_NAMES:
            result = f"_{result}"
    else:
        result = filename
        for c in _POSIX_FORBIDDEN_CHARS:
            result = result.replace(c, "_")

    # 长度限制（大多数文件系统限制 255 字节）
    if len(result.encode("utf-8")) > 255:
        # 逐字符截断，确保不超过 255 字节
        truncated = ""
        for char in result:
            if len((truncated + char).encode("utf-8")) > 251:  # 留 4 字节余量
                break
            truncated += char
        result = truncated

    return result or "unnamed"


def sanitize_filename_cross_platform(filename: str) -> str:
    """
    跨平台清理文件名

    不管当前平台是什么，同时应用 Windows + POSIX 的限制。
    适用于需要在多平台间共享的文件。

    Args:
        filename: 原始文件名

    Returns:
        在所有平台都安全的文件名
    """
    if not filename:
        return "unnamed"

    result = filename

    # 应用所有禁止字符
    all_forbidden = _WINDOWS_FORBIDDEN_CHARS | _POSIX_FORBIDDEN_CHARS
    for c in all_forbidden:
        result = result.replace(c, "_")

    # Windows 末尾限制
    result = result.rstrip(". ")

    # Windows 保留名称
    stem = Path(result).stem.upper()
    if stem in _WINDOWS_RESERVED_NAMES:
        result = f"_{result}"

    # 长度限制
    if len(result.encode("utf-8")) > 255:
        truncated = ""
        for char in result:
            if len((truncated + char).encode("utf-8")) > 251:
                break
            truncated += char
        result = truncated

    return result or "unnamed"


# ═══════════════════════════════════════════════════════
#  路径工具
# ═══════════════════════════════════════════════════════

def normalize_path_separators(path: str) -> str:
    """
    规范化路径分隔符

    Windows: 反斜杠 → 正斜杠（Python Path 两种都支持，统一为正斜杠方便显示）
    POSIX: 无变化

    注意: 只做显示用途的规范化，实际文件操作用 Path 对象。

    Args:
        path: 原始路径字符串

    Returns:
        规范化后的路径字符串
    """
    if IS_WINDOWS:
        return path.replace("\\", "/")
    return path


def get_path_max_length() -> int:
    """
    获取当前平台的最大路径长度

    Windows: 260 (MAX_PATH)，启用长路径后为 32767
    POSIX: 4096 (PATH_MAX)

    Returns:
        最大路径长度（字符数）
    """
    if IS_WINDOWS:
        # 检查是否启用了长路径支持
        try:
            import ctypes
            ntdll = ctypes.WinDLL("ntdll")  # type: ignore[attr-defined]
            if hasattr(ntdll, "RtlAreLongPathsEnabled"):
                enabled = ctypes.c_bool()
                ntdll.RtlAreLongPathsEnabled(ctypes.byref(enabled))
                if enabled.value:
                    return 32767
        except (AttributeError, OSError):
            pass
        return 260
    return 4096
