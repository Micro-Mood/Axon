"""
Layer 1: Core — 安全校验器

纯校验逻辑，无状态。
不包含文件操作、文件锁、校验和计算（那些归 handler / platform）。

依赖:
- config.SecurityConfig (结构)
- errors (异常类型)
- 注意: 不依赖 platform 层 — platform 相关校验由 middleware 或上层协调
"""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path

from .config import SecurityConfig
from .errors import (
    BlockedCommandError,
    BlockedPathError,
    InvalidParameterError,
    PathOutsideWorkspaceError,
    PermissionDeniedError,
    SizeLimitExceededError,
    SymlinkError,
)

# ═══════════════════════════════════════════════════════
#  常量
# ═══════════════════════════════════════════════════════

# 危险环境变量 — 设置这些可以劫持进程行为
_DANGEROUS_ENV_KEYS = frozenset({
    # Unix: 动态链接劫持
    "LD_PRELOAD", "LD_LIBRARY_PATH",
    "DYLD_INSERT_LIBRARIES", "DYLD_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH",
    # 执行路径劫持
    "PATH",
    # Python 相关
    "PYTHONPATH", "PYTHONSTARTUP", "PYTHONHOME",
    # Ruby/Node/Perl
    "RUBYLIB", "NODE_PATH", "PERL5LIB",
    # 权限提升
    "SUDO_ASKPASS",
    # Shell 配置
    "ENV", "BASH_ENV", "CDPATH", "IFS",
})

# ── 危险命令模式 ──
# 分类组织，每条正则对应一个具体攻击向量。
# 预编译，匹配时 O(1) 查找。
#
# 类型标签用于日志和错误信息，便于排查被拦截的原因。

_DangerousPattern = tuple[str, re.Pattern[str]]  # (label, compiled_regex)


def _compile_patterns(patterns: list[tuple[str, str]]) -> list[_DangerousPattern]:
    """预编译危险模式列表"""
    return [(label, re.compile(regex, re.IGNORECASE)) for label, regex in patterns]


_DANGEROUS_PATTERNS: list[_DangerousPattern] = _compile_patterns([
    # ── 命令链接到危险命令 ──
    ("chain_to_destructive",   r'&&\s*(?:del|rd|rmdir|format|diskpart|rm|dd|mkfs)'),
    ("pipe_to_destructive",    r'\|\s*(?:del|rd|rm|dd|format)'),
    ("semicolon_chain",        r';\s*(?:del|rd|rm|dd|format|mkfs)'),

    # ── 设备/空设备重定向 ──
    ("device_redirect",        r'>\s*(?:con|nul|prn|aux|com\d|lpt\d|/dev/)'),

    # ── Shell 命令注入 ──
    ("backtick_injection",     r'`[^`]+`'),
    ("dollar_paren_injection", r'\$\([^)]+\)'),
    ("dollar_brace_injection", r'\$\{[^}]+\}'),

    # ── 递归删除 ──
    ("win_del_recursive",      r'\bdel\s+/[sfq]'),
    ("win_rd_recursive",       r'\brd\s+/[sq]'),
    ("unix_rm_recursive",      r'\brm\s+-[rf]+'),
    ("unix_rm_no_preserve",    r'\brm\s+--no-preserve-root'),

    # ── 磁盘/分区操作 ──
    ("win_format_drive",       r'\bformat\s+[a-z]:'),
    ("win_diskpart",           r'\bdiskpart'),
    ("unix_dd_write",          r'\bdd\s+.*of='),
    ("unix_mkfs",              r'\bmkfs\.'),

    # ── 网络攻击向量 ──
    ("netcat_listen",          r'\bnc\s+-[el]'),
    ("curl_pipe_exec",         r'\bcurl\s+.*\|\s*(?:bash|sh|powershell)'),
    ("wget_pipe_exec",         r'\bwget\s+.*\|\s*(?:bash|sh)'),

    # ── PowerShell 危险操作 ──
    ("ps_invoke_expression",   r'invoke-expression'),
    ("ps_iex",                 r'\biex\s*\('),
    ("ps_encoded_command",     r'-encodedcommand'),
    ("ps_downloadstring",      r'downloadstring'),
    ("ps_bypass_policy",       r'-(?:ep|executionpolicy)\s+bypass'),
    ("ps_hidden_window",       r'-(?:w|windowstyle)\s+hidden'),

    # ── Windows 注册表 ──
    ("reg_delete",             r'\breg\s+delete'),
    ("reg_add_force",          r'\breg\s+add\s+.*\/f'),

    # ── 系统级危险命令 ──
    ("win_bcdedit",            r'\bbcdedit\b'),
    ("win_shutdown",           r'\bshutdown\b'),
    ("win_taskkill_force",     r'\btaskkill\s+/f'),
    ("unix_chmod_suid",        r'\bchmod\s+[ugo]*\+s'),
    ("unix_chown_root",        r'\bchown\s+root'),

    # ── 用户/权限操作 ──
    ("win_net_user",           r'\bnet\s+user\b'),
    ("win_net_localgroup",     r'\bnet\s+localgroup\b'),
    ("win_runas",              r'\brunas\b'),
    ("unix_sudo_su",           r'\bsudo\s+su\b'),
    ("unix_passwd",            r'\bpasswd\b'),

    # ── 反弹 shell ──
    ("reverse_shell_bash",     r'\bbash\s+-i\s+>'),
    ("reverse_shell_devtcp",   r'/dev/tcp/'),
    ("reverse_shell_python",   r'python.*\bsocket\b.*\bconnect\b'),

    # ── 环境变量展开（Windows cmd.exe 注入向量） ──
    ("win_env_expansion",      r'%[a-zA-Z_][a-zA-Z0-9_]*%'),
])


class SecurityChecker:
    """
    无状态安全校验器

    所有方法都是纯校验: 输入 → 通过 / 抛异常
    不做任何 I/O 操作
    """

    def __init__(self, config: SecurityConfig):
        self._config = config
        # 预编译 blocked_commands 的正则匹配
        self._blocked_cmd_patterns: list[re.Pattern] = [
            re.compile(re.escape(cmd), re.IGNORECASE)
            for cmd in config.blocked_commands
        ]

    # ── 路径校验 ──

    def validate_path(self, path: str, workspace: Path) -> Path:
        """
        校验路径安全性，返回解析后的绝对路径

        检查顺序:
        1. 解析为绝对路径
        2. 检查是否在 workspace 内
        3. 检查是否在 blocked_paths 中
        4. 检查符号链接

        Args:
            path: 原始路径（相对或绝对）
            workspace: 工作区根路径（已 resolve）

        Returns:
            验证通过的绝对路径

        Raises:
            PathOutsideWorkspaceError
            BlockedPathError
            SymlinkError
        """
        # 解析为绝对路径
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = workspace / resolved
        resolved = resolved.resolve()

        # workspace 边界检查
        try:
            resolved.relative_to(workspace)
        except ValueError:
            raise PathOutsideWorkspaceError(
                f"路径不在工作区内: {path}",
                details={"path": str(resolved), "workspace": str(workspace)},
            )

        # blocked_paths 检查
        resolved_str = str(resolved)
        for blocked in self._config.blocked_paths:
            blocked_resolved = str(Path(blocked).resolve())
            if resolved_str == blocked_resolved or resolved_str.startswith(
                blocked_resolved + os.sep
            ):
                raise BlockedPathError(
                    f"路径被禁止访问: {path}",
                    details={"path": resolved_str, "blocked_by": blocked},
                )

        # 符号链接检查
        if not self._config.follow_symlinks and Path(path).is_symlink():
            real_target = Path(path).resolve()
            try:
                real_target.relative_to(workspace)
            except ValueError:
                raise SymlinkError(
                    f"符号链接指向工作区外: {path} → {real_target}",
                    details={
                        "symlink": str(path),
                        "target": str(real_target),
                        "workspace": str(workspace),
                    },
                    suggestion="设置 follow_symlinks=true 或将目标移入工作区",
                )

        return resolved

    def check_read_permission(self, path: Path) -> None:
        """检查文件是否可读"""
        if path.exists() and not os.access(path, os.R_OK):
            raise PermissionDeniedError(
                f"无读取权限: {path}",
                details={"path": str(path)},
            )

    def check_write_permission(self, path: Path) -> None:
        """检查文件/目录是否可写"""
        # 文件存在 → 检查文件本身
        if path.exists():
            if not os.access(path, os.W_OK):
                raise PermissionDeniedError(
                    f"无写入权限: {path}",
                    details={"path": str(path)},
                )
        else:
            # 文件不存在 → 检查父目录
            parent = path.parent
            if parent.exists() and not os.access(parent, os.W_OK):
                raise PermissionDeniedError(
                    f"无法在目录中创建文件: {parent}",
                    details={"path": str(path), "parent": str(parent)},
                )

    # ── 命令校验 ──

    def validate_command(self, command: str) -> None:
        """
        校验命令安全性

        三层检查:
        1. Shell 语法检查（引号闭合、转义完整性）
        2. 黑名单命令匹配（配置文件 blocked_commands）
        3. 危险模式扫描（预编译正则，覆盖注入/提权/磁盘操作等 40+ 种向量）

        Raises:
            InvalidParameterError: shell 语法错误
            BlockedCommandError: 命令在黑名单中或匹配危险模式
        """
        # ── 1. 语法预检 ──
        self._check_shell_syntax(command)

        # ── 2. 黑名单匹配 ──
        for i, pattern in enumerate(self._blocked_cmd_patterns):
            if pattern.search(command):
                raise BlockedCommandError(
                    f"命令被禁止: {command}",
                    details={
                        "command": command,
                        "blocked_by": self._config.blocked_commands[i],
                    },
                )

        # ── 3. 危险模式扫描 ──
        command_lower = command.lower()
        for label, pattern in _DANGEROUS_PATTERNS:
            if pattern.search(command_lower):
                raise BlockedCommandError(
                    f"检测到危险命令模式: {command}",
                    details={
                        "command": command[:500],
                        "pattern_label": label,
                    },
                    suggestion="该命令包含可能导致系统损坏或安全风险的操作",
                )

    def validate_cwd(self, cwd: str, workspace: Path) -> Path:
        """
        校验工作目录安全性

        工作目录必须:
        1. 存在且是目录
        2. 在 workspace 范围内
        3. 不在 blocked_paths 中

        Args:
            cwd: 工作目录路径字符串
            workspace: 工作区根路径

        Returns:
            验证通过的绝对路径

        Raises:
            InvalidParameterError: 路径不存在/不是目录
            PathOutsideWorkspaceError: 不在 workspace 内
            BlockedPathError: 在黑名单中
        """
        resolved = Path(cwd).resolve()

        if not resolved.exists():
            raise InvalidParameterError(
                f"工作目录不存在: {cwd}",
                details={"cwd": str(resolved)},
            )
        if not resolved.is_dir():
            raise InvalidParameterError(
                f"工作目录不是目录: {cwd}",
                details={"cwd": str(resolved)},
            )

        # workspace 边界检查
        try:
            resolved.relative_to(workspace)
        except ValueError:
            raise PathOutsideWorkspaceError(
                f"工作目录不在工作区内: {cwd}",
                details={"cwd": str(resolved), "workspace": str(workspace)},
            )

        # blocked_paths 检查
        resolved_str = str(resolved)
        for blocked in self._config.blocked_paths:
            blocked_resolved = str(Path(blocked).resolve())
            if resolved_str == blocked_resolved or resolved_str.startswith(
                blocked_resolved + os.sep
            ):
                raise BlockedPathError(
                    f"工作目录被禁止: {cwd}",
                    details={"cwd": resolved_str, "blocked_by": blocked},
                )

        return resolved

    def validate_env(self, env: dict[str, str]) -> None:
        """
        校验环境变量安全性

        禁止修改高危环境变量（PATH, LD_PRELOAD 等）。

        Args:
            env: 待注入的环境变量字典

        Raises:
            InvalidParameterError: 包含危险环境变量
        """
        if not env:
            return

        dangerous_found = []
        for key in env:
            if key.upper() in _DANGEROUS_ENV_KEYS:
                dangerous_found.append(key)

        if dangerous_found:
            raise InvalidParameterError(
                f"包含危险环境变量: {', '.join(dangerous_found)}",
                details={
                    "dangerous_keys": dangerous_found,
                    "blocked_keys": sorted(_DANGEROUS_ENV_KEYS),
                },
                suggestion="这些环境变量可能被用于劫持进程行为，禁止通过 API 设置",
            )

    @staticmethod
    def _check_shell_syntax(command: str) -> None:
        """
        检查 shell 命令的语法完整性

        使用 shlex.split() 做词法分析，检测:
        - 未闭合的单引号: echo it's done
        - 未闭合的双引号: echo "hello
        - 未闭合的反引号: echo `whoami
        - 行尾悬空反斜杠: echo hello\\

        注意: shlex 是 POSIX shell 语法。Windows cmd.exe 的语法不同，
        但 asyncio.create_subprocess_shell 在 Windows 上也是通过
        cmd.exe /c 执行，其引号规则更宽松，这里的检查偏保守。

        Args:
            command: shell 命令字符串

        Raises:
            InvalidParameterError: 语法不完整
        """
        if not command or not command.strip():
            raise InvalidParameterError(
                "命令不能为空",
                details={"command": command},
            )

        try:
            shlex.split(command)
        except ValueError as e:
            # shlex 会抛出:
            # "No closing quotation" — 引号未闭合
            # "No escaped character" — 尾部悬空反斜杠
            raise InvalidParameterError(
                f"Shell 命令语法错误: {e}",
                details={"command": command[:500]},
                suggestion="检查引号是否闭合，反斜杠后是否有字符",
            )

    def validate_shell(self, shell: str) -> None:
        """
        校验 shell 是否在允许列表中

        Raises:
            BlockedCommandError
        """
        if self._config.allowed_shells:
            shell_name = Path(shell).name.lower()
            allowed_names = [Path(s).name.lower() for s in self._config.allowed_shells]
            if shell_name not in allowed_names:
                raise BlockedCommandError(
                    f"Shell 不在允许列表中: {shell}",
                    details={
                        "shell": shell,
                        "allowed": self._config.allowed_shells,
                    },
                )

    # ── 文件大小校验 ──

    def check_file_size(self, path: Path) -> None:
        """
        检查文件大小是否超限

        Raises:
            SizeLimitExceededError
        """
        if not path.exists():
            return
        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > self._config.max_file_size_mb:
            raise SizeLimitExceededError(
                f"文件过大: {size_mb:.1f}MB (限制 {self._config.max_file_size_mb}MB)",
                details={
                    "path": str(path),
                    "size_mb": round(size_mb, 2),
                    "limit_mb": self._config.max_file_size_mb,
                },
            )
