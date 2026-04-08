"""
Layer 2: Platform — 平台抽象层

所有平台差异的唯一出口。
其他层（handlers, middleware, protocol）禁止出现 sys.platform / os.name 判断。

使用方式:
    from mcp.platform import (
        IS_WINDOWS, IS_LINUX, IS_MACOS,
        decode_output, get_console_encoding,
        is_hidden, sanitize_filename,
        send_interrupt, graceful_stop,
        default_blocked_paths, default_shells,
    )
"""

import sys

# ═══════════════════════════════════════════════════════
#  平台标识（全局常量）
# ═══════════════════════════════════════════════════════

IS_WINDOWS: bool = sys.platform == "win32"
IS_LINUX: bool = sys.platform == "linux"
IS_MACOS: bool = sys.platform == "darwin"
IS_POSIX: bool = IS_LINUX or IS_MACOS

# ═══════════════════════════════════════════════════════
#  编码 (encoding.py)
# ═══════════════════════════════════════════════════════

from .encoding import (
    IncrementalStreamDecoder,
    decode_output,
    detect_file_encoding,
    encode_input,
    get_console_encoding,
    has_control_chars,
    reset_console_encoding_cache,
    safe_encode,
    safe_truncate_bytes,
    sanitize_control_chars,
    validate_encoding,
)

# ═══════════════════════════════════════════════════════
#  进程信号 (signal.py)
# ═══════════════════════════════════════════════════════

from .signal import (
    SIGNAL_INTERRUPT,
    SIGNAL_KILL,
    SIGNAL_TERMINATE,
    force_kill,
    graceful_stop,
    normalize_signal_name,
    send_interrupt,
    send_signal_by_name,
    send_terminate,
)

# ═══════════════════════════════════════════════════════
#  文件系统 (filesystem.py)
# ═══════════════════════════════════════════════════════

from .filesystem import (
    get_file_attributes,
    get_file_attributes_from_stat,
    get_path_max_length,
    is_hidden,
    normalize_path_separators,
    sanitize_filename,
    sanitize_filename_cross_platform,
)

# ═══════════════════════════════════════════════════════
#  安全默认值 & 事件循环 (defaults.py)
# ═══════════════════════════════════════════════════════

from .defaults import (
    create_event_loop_for_subprocess,
    default_blocked_commands,
    default_blocked_paths,
    default_shell,
    default_shells,
    get_subprocess_creation_flags,
)

# ═══════════════════════════════════════════════════════
#  __all__
# ═══════════════════════════════════════════════════════

__all__ = [
    # 平台标识
    "IS_WINDOWS",
    "IS_LINUX",
    "IS_MACOS",
    "IS_POSIX",
    # 编码
    "get_console_encoding",
    "decode_output",
    "detect_file_encoding",
    "safe_encode",
    "validate_encoding",
    "encode_input",
    "IncrementalStreamDecoder",
    "safe_truncate_bytes",
    "sanitize_control_chars",
    "has_control_chars",
    "reset_console_encoding_cache",
    # 进程信号
    "SIGNAL_INTERRUPT",
    "SIGNAL_TERMINATE",
    "SIGNAL_KILL",
    "send_interrupt",
    "send_terminate",
    "force_kill",
    "send_signal_by_name",
    "normalize_signal_name",
    "graceful_stop",
    # 文件系统
    "is_hidden",
    "get_file_attributes",
    "get_file_attributes_from_stat",
    "sanitize_filename",
    "sanitize_filename_cross_platform",
    "normalize_path_separators",
    "get_path_max_length",
    # 安全默认值
    "default_blocked_paths",
    "default_blocked_commands",
    "default_shells",
    "default_shell",
    # 事件循环
    "create_event_loop_for_subprocess",
    "get_subprocess_creation_flags",
]
