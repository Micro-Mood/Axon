"""
Layer 2: Platform — 进程信号处理

职责:
- 跨平台发送中断/终止/强杀信号
- 统一信号名称（Windows CTRL_C ↔ POSIX SIGINT）
- 优雅停止 + 超时强杀

Windows:
  - CTRL_C_EVENT  → 优雅中断（相当于 SIGINT）
  - CTRL_BREAK_EVENT → 强制终止（相当于 SIGTERM）
  - process.kill() → 强制杀死

POSIX (Linux/macOS):
  - SIGINT  → 优雅中断
  - SIGTERM → 请求终止
  - SIGKILL → 强制杀死
"""

from __future__ import annotations

import asyncio
import signal
import sys

IS_WINDOWS = sys.platform == "win32"


# ═══════════════════════════════════════════════════════
#  信号名称规范化
# ═══════════════════════════════════════════════════════

# 标准化信号名称: 各种别名 → 统一名称
_SIGNAL_ALIASES: dict[str, str] = {
    # interrupt 类
    "interrupt": "interrupt",
    "int": "interrupt",
    "sigint": "interrupt",
    "ctrl_c": "interrupt",
    "ctrl+c": "interrupt",
    "ctrl-c": "interrupt",
    "ctrl_c_event": "interrupt",
    # terminate 类
    "terminate": "terminate",
    "term": "terminate",
    "sigterm": "terminate",
    "ctrl_break": "terminate",
    "ctrl+break": "terminate",
    "ctrl-break": "terminate",
    "ctrl_break_event": "terminate",
    # kill 类
    "kill": "kill",
    "sigkill": "kill",
    "force": "kill",
    "force_kill": "kill",
}

# 合法的标准化名称
SIGNAL_INTERRUPT = "interrupt"
SIGNAL_TERMINATE = "terminate"
SIGNAL_KILL = "kill"


def normalize_signal_name(name: str) -> str:
    """
    将各种信号名称别名统一为标准名称

    支持的输入 (大小写不敏感):
      "CTRL_C", "SIGINT", "interrupt", "int" → "interrupt"
      "CTRL_BREAK", "SIGTERM", "terminate", "term" → "terminate"
      "SIGKILL", "kill", "force", "force_kill" → "kill"

    Args:
        name: 原始信号名称

    Returns:
        标准化名称: "interrupt" | "terminate" | "kill"

    Raises:
        ValueError: 无法识别的信号名称
    """
    normalized = _SIGNAL_ALIASES.get(name.lower().strip())
    if normalized is None:
        valid = sorted(set(_SIGNAL_ALIASES.values()))
        raise ValueError(
            f"无法识别的信号名称: {name!r}，"
            f"有效值: {', '.join(valid)} "
            f"(或其别名: {', '.join(sorted(_SIGNAL_ALIASES.keys()))})"
        )
    return normalized


# ═══════════════════════════════════════════════════════
#  信号发送
# ═══════════════════════════════════════════════════════

def send_interrupt(process: asyncio.subprocess.Process) -> bool:
    """
    发送中断信号（优雅停止）

    Windows: CTRL_C_EVENT
    POSIX:   SIGINT

    Args:
        process: asyncio 子进程

    Returns:
        True 发送成功, False 失败（进程已退出等）
    """
    try:
        if IS_WINDOWS:
            process.send_signal(signal.CTRL_C_EVENT)
        else:
            process.send_signal(signal.SIGINT)
        return True
    except (ProcessLookupError, OSError):
        # 进程已退出
        return False


def send_terminate(process: asyncio.subprocess.Process) -> bool:
    """
    发送终止信号

    Windows: CTRL_BREAK_EVENT
    POSIX:   SIGTERM

    Args:
        process: asyncio 子进程

    Returns:
        True 发送成功, False 失败
    """
    try:
        if IS_WINDOWS:
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.send_signal(signal.SIGTERM)
        return True
    except (ProcessLookupError, OSError):
        return False


def force_kill(process: asyncio.subprocess.Process) -> bool:
    """
    强制杀死进程

    Windows: TerminateProcess (通过 process.kill())
    POSIX:   SIGKILL (通过 process.kill())

    两个平台 process.kill() 的行为一致。

    Args:
        process: asyncio 子进程

    Returns:
        True 发送成功, False 失败
    """
    try:
        process.kill()
        return True
    except (ProcessLookupError, OSError):
        return False


def send_signal_by_name(
    process: asyncio.subprocess.Process,
    signal_name: str,
) -> bool:
    """
    按标准化名称发送信号

    会先调用 normalize_signal_name() 统一名称，然后分发。

    Args:
        process: asyncio 子进程
        signal_name: 信号名称（支持别名，大小写不敏感）

    Returns:
        True 发送成功, False 失败

    Raises:
        ValueError: 无法识别的信号名称
    """
    name = normalize_signal_name(signal_name)
    if name == SIGNAL_INTERRUPT:
        return send_interrupt(process)
    elif name == SIGNAL_TERMINATE:
        return send_terminate(process)
    else:
        return force_kill(process)


# ═══════════════════════════════════════════════════════
#  优雅停止（带超时强杀）
# ═══════════════════════════════════════════════════════

async def graceful_stop(
    process: asyncio.subprocess.Process,
    timeout: float = 5.0,
) -> tuple[str, int | None]:
    """
    优雅停止进程：先 interrupt → 等待 → 超时则 terminate → 再等 → force kill

    三阶段递进:
    1. send_interrupt → 等 timeout 秒
    2. 未退出 → send_terminate → 再等 timeout 秒
    3. 仍未退出 → force_kill

    Args:
        process: asyncio 子进程
        timeout: 每阶段的等待秒数

    Returns:
        (stop_method, exit_code)
        - stop_method: "interrupt" | "terminate" | "kill" | "already_exited"
        - exit_code: 进程退出码，None 表示未知
    """
    # 检查是否已经退出
    if process.returncode is not None:
        return ("already_exited", process.returncode)

    # 阶段 1: interrupt
    send_interrupt(process)
    try:
        exit_code = await asyncio.wait_for(process.wait(), timeout=timeout)
        return ("interrupt", exit_code)
    except asyncio.TimeoutError:
        pass

    # 阶段 2: terminate
    send_terminate(process)
    try:
        exit_code = await asyncio.wait_for(process.wait(), timeout=timeout)
        return ("terminate", exit_code)
    except asyncio.TimeoutError:
        pass

    # 阶段 3: force kill
    force_kill(process)
    try:
        exit_code = await asyncio.wait_for(process.wait(), timeout=2.0)
        return ("kill", exit_code)
    except asyncio.TimeoutError:
        return ("kill", None)
