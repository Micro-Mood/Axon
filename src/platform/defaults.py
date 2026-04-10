"""
Layer 2: Platform — 安全默认值

职责:
- 提供各平台的默认 blocked_paths
- 提供各平台的默认 blocked_commands
- 提供各平台的默认 allowed_shells
- 提供默认 shell 路径
- 提供事件循环相关工具

这些默认值在 config 未指定时使用，由 middleware 或初始化代码注入到 SecurityConfig 中。
"""

from __future__ import annotations

import asyncio
import sys

IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform == "linux"
IS_MACOS = sys.platform == "darwin"


# ═══════════════════════════════════════════════════════
#  默认安全路径黑名单
# ═══════════════════════════════════════════════════════

def default_blocked_paths() -> list[str]:
    """
    获取当前平台的默认路径黑名单

    这些路径不应被 MCP 工具读写:
    - Windows: 系统目录、Program Files、回收站等
    - Linux: /proc, /sys, /dev, /boot, 敏感配置文件等
    - macOS: 类似 Linux + /System, /Library 等

    Returns:
        路径字符串列表
    """
    if IS_WINDOWS:
        import os as _os
        _sysroot = _os.environ.get('SystemRoot', 'C:\\Windows')
        _progfiles = _os.environ.get('ProgramFiles', 'C:\\Program Files')
        _progfiles86 = _os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)')
        _programdata = _os.environ.get('ProgramData', 'C:\\ProgramData')
        _sysdrive = _os.environ.get('SystemDrive', 'C:')
        return [
            # 系统核心
            _sysroot,
            _os.path.join(_sysroot, "System32"),
            _os.path.join(_sysroot, "SysWOW64"),
            # 程序目录
            _progfiles,
            _progfiles86,
            _programdata,
            # 引导和恢复
            _sysdrive + "\\Boot",
            _sysdrive + "\\Recovery",
            _sysdrive + "\\System Volume Information",
            # 回收站
            _sysdrive + "\\$Recycle.Bin",
            # EFI 分区
            _sysdrive + "\\EFI",
        ]
    elif IS_MACOS:
        return [
            # 内核虚拟文件系统
            "/proc",
            "/sys",
            "/dev",
            # 引导
            "/boot",
            # root 家目录
            "/root",
            # 敏感配置
            "/etc/shadow",
            "/etc/passwd",
            "/etc/sudoers",
            "/etc/ssh",
            # 运行时
            "/var/run",
            "/run",
            # macOS 系统
            "/System",
            "/Library",
            "/private/var/db",
        ]
    else:
        # Linux
        return [
            # 内核虚拟文件系统
            "/proc",
            "/sys",
            "/dev",
            # 引导
            "/boot",
            # root 家目录
            "/root",
            # 敏感配置
            "/etc/shadow",
            "/etc/passwd",
            "/etc/sudoers",
            "/etc/ssh",
            # 运行时
            "/var/run",
            "/run",
            # snap 和 systemd
            "/snap",
        ]


# ═══════════════════════════════════════════════════════
#  默认命令黑名单
# ═══════════════════════════════════════════════════════

def default_blocked_commands() -> list[str]:
    """
    获取当前平台的默认命令黑名单

    这些命令/命令片段会被 SecurityChecker 拒绝执行:
    - Windows: 格式化、注册表、磁盘管理、关机等
    - Linux: rm -rf /, mkfs, dd, fork bomb 等

    Returns:
        命令/命令片段字符串列表（SecurityChecker 会做子串匹配）
    """
    if IS_WINDOWS:
        return [
            # 磁盘操作
            "format",
            "diskpart",
            # 删除操作
            "del /s",
            "del /q /s",
            "rd /s",
            "rmdir /s",
            # 注册表
            "reg delete",
            "reg add",
            # 引导
            "bcdedit",
            "bootrec",
            # 系统控制
            "shutdown",
            "restart",
            # 进程管理（危险用法）
            "taskkill /f /im",
            # 用户管理
            "net user",
            "net localgroup",
            # 提权
            "runas",
            # PowerShell 绕过
            "powershell -ep bypass",
            "powershell -executionpolicy bypass",
            "powershell -enc",
            "powershell -encodedcommand",
            # WMI
            "wmic",
        ]
    else:
        return [
            # 递归删除根目录
            "rm -rf /",
            "rm -rf /*",
            "rm -rf ~",
            # 格式化
            "mkfs",
            # 磁盘写入
            "dd if=",
            "dd of=/dev/",
            # 权限破坏
            "chmod 000 /",
            "chmod -R 000",
            "chmod 777 /",
            "chmod -R 777",
            # 所有权更改
            "chown root",
            # 系统控制
            "shutdown",
            "reboot",
            "halt",
            "init 0",
            "init 6",
            "systemctl poweroff",
            "systemctl reboot",
            # fork bomb
            ":(){ :|:& };:",
            # 根目录移动
            "mv / ",
            "mv /* ",
            # 远程代码执行
            "wget|sh",
            "curl|sh",
            "wget -O -|sh",
            "curl -s|sh",
            # 反弹 shell
            "/dev/tcp/",
            "bash -i >& /dev/",
            # crontab 清除
            "crontab -r",
        ]


# ═══════════════════════════════════════════════════════
#  默认 Shell 白名单
# ═══════════════════════════════════════════════════════

def default_shells() -> list[str]:
    """
    获取当前平台的默认允许 shell 列表

    只有这些 shell 才允许执行命令。

    Returns:
        Shell 路径/名称列表
    """
    if IS_WINDOWS:
        return [
            "cmd.exe",
            "powershell.exe",
            "pwsh.exe",
        ]
    else:
        return [
            "/bin/bash",
            "/bin/sh",
            "/usr/bin/bash",
            "/usr/bin/sh",
            "/usr/bin/zsh",
            "bash",
            "sh",
            "zsh",
        ]


def default_shell() -> str:
    """
    获取当前平台的默认 shell

    Returns:
        默认 shell 路径或名称
    """
    if IS_WINDOWS:
        return "cmd.exe"
    return "/bin/bash"


# ═══════════════════════════════════════════════════════
#  事件循环
# ═══════════════════════════════════════════════════════

def create_event_loop_for_subprocess() -> asyncio.AbstractEventLoop | None:
    """
    为子线程创建适合子进程管理的事件循环

    背景:
    - Windows 默认 ProactorEventLoop 支持子进程，但在子线程中
      有管道写入竞争 bug（asyncio known issue）
    - 子线程改用 SelectorEventLoop 更稳定
    - Linux 的 SelectorEventLoop 天然支持子进程，无需特殊处理

    用法:
        loop = create_event_loop_for_subprocess()
        if loop:
            # Windows 子线程: 手动管理 loop
            loop.run_until_complete(my_coro())
            loop.close()
        else:
            # Linux: 用 asyncio.run()
            asyncio.run(my_coro())

    Returns:
        Windows 返回 SelectorEventLoop 实例（已设为当前线程 loop）
        Linux 返回 None（直接用 asyncio.run 即可）
    """
    if IS_WINDOWS:
        loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(loop)
        return loop
    return None


def get_subprocess_creation_flags() -> int:
    """
    获取创建子进程时需要的平台特定标志

    Windows:
    - CREATE_NO_WINDOW: 不弹出控制台窗口
    - CREATE_NEW_PROCESS_GROUP: 新进程组（允许发送 CTRL_C_EVENT）

    Linux:
    - 0（无额外标志）

    Returns:
        用于 subprocess.Popen / asyncio.create_subprocess_* 的 creationflags
    """
    if IS_WINDOWS:
        import subprocess
        return (
            subprocess.CREATE_NO_WINDOW
            | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    return 0
