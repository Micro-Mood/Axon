"""
Layer 4: Handlers — 命令执行与进程管理

同步执行:
  run(command, cwd, timeout, env) → 执行命令并等待完成

异步任务生命周期:
  spawn(command, cwd, timeout, env) → 创建并启动任务，返回 task_id
  stop(task_id, force)              → 停止任务（force=True 强制终止）
  delete_task(task_id)              → 删除已完成任务，释放内存
  status(task_id)                   → 查询状态
  wait(task_id, timeout)            → 等待完成
  list()                            → 列出所有任务

流式 I/O:
  read_stdout(task_id, max_chars)   → 读取标准输出
  read_stderr(task_id, max_chars)   → 读取标准错误
  write_stdin(task_id, data, eof)   → 写入标准输入

依赖:
- Layer 1: core (MCPConfig, CacheManager, errors)
- Layer 2: platform (signal, defaults)
- Layer 3: stream (StreamManager)
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.cache import CacheManager
from ..core.config import MCPConfig
from ..core.errors import (
    InvalidParameterError,
    MaxConcurrentTasksError,
    TaskAlreadyRunningError,
    TaskFailedError,
    TaskNotFoundError,
    TimeoutError,
    WARNING_OUTPUT_TRUNCATED,
    WARNING_SLOW_OPERATION,
)
from ..core.security import SecurityChecker
from ..platform import (
    default_shell,
    encode_input,
    force_kill,
    get_subprocess_creation_flags,
    send_signal_by_name,
)
from ..stream import StreamManager
from .base import BaseHandler, RequestContext, Task, TaskState

logger = logging.getLogger(__name__)

_SAFE_ENV_KEYS = frozenset({
    "PATH", "HOME", "USER", "LOGNAME", "SHELL",
    "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TMPDIR",
    "SYSTEMROOT", "COMSPEC", "PATHEXT", "TEMP", "TMP",
    "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "PROGRAMDATA",
})


class CommandHandler(BaseHandler):
    """
    命令执行与进程管理 handler

    额外依赖: StreamManager（通过构造函数注入）
    """

    def __init__(
        self,
        config: MCPConfig,
        cache: CacheManager,
        stream_manager: StreamManager,
        security: SecurityChecker | None = None,
    ):
        super().__init__(config, cache)
        self._stream = stream_manager
        self._security = security
        self._tasks: dict[str, Task] = {}
        self._timeout_tasks: dict[str, asyncio.Task[None]] = {}

    # ═══════════════════════════════════════════════════
    #  同步执行
    # ═══════════════════════════════════════════════════

    async def run(
        self,
        ctx: RequestContext,
        command: str,
        cwd: str | None = None,
        timeout: int | None = None,
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        同步执行命令并等待完成

        本质是 spawn → wait → finalize → cleanup 的快捷方式。

        Args:
            command: 要执行的命令
            cwd: 工作目录，None 使用 workspace
            timeout: 超时毫秒数，None 使用配置默认值
            env: 额外环境变量

        Returns:
            {task_id, command, exit_code, stdout, stderr, duration_ms, warnings}
        """
        timeout_ms = timeout or self.config.performance.default_timeout_ms

        # spawn
        task_id = await self._do_spawn(command, cwd, env, timeout_ms=None)
        task = self._tasks[task_id]

        # wait
        try:
            await asyncio.wait_for(
                task.process.wait(),
                timeout=timeout_ms / 1000.0,
            )
        except asyncio.TimeoutError:
            # 超时 → 强制终止
            self._complete_task(task, TaskState.TIMED_OUT)
            force_kill(task.process)
            await self._safe_wait(task.process, 3.0)

        # finalize
        output = await self._stream.finalize(task_id)
        self._stream.cleanup(task_id)

        # 更新任务状态（如果还没被 timeout 设置过）
        if task.is_active:
            exit_code = task.process.returncode
            task.exit_code = exit_code
            state = TaskState.COMPLETED if exit_code == 0 else TaskState.FAILED
            self._complete_task(task, state)

        # 截断警告
        stdout_buf = output.get("stdout_summary", {})
        stderr_buf = output.get("stderr_summary", {})
        if stdout_buf.get("truncated") or stderr_buf.get("truncated"):
            ctx.warn(
                WARNING_OUTPUT_TRUNCATED,
                "命令输出超过缓冲区限制，已截断",
                stdout_truncated=stdout_buf.get("truncated", False),
                stderr_truncated=stderr_buf.get("truncated", False),
            )

        # 慢操作警告
        if task.duration_ms and task.duration_ms > 5000:
            ctx.warn(
                WARNING_SLOW_OPERATION,
                f"命令执行耗时 {task.duration_ms:.0f}ms",
                duration_ms=round(task.duration_ms),
            )

        result = {
            "task_id": task_id,
            "command": command,
            "exit_code": task.exit_code,
            "stdout": output.get("stdout", ""),
            "stderr": output.get("stderr", ""),
            "duration_ms": task.duration_ms,
        }

        # 清理任务记录
        self._tasks.pop(task_id, None)

        return result

    # ═══════════════════════════════════════════════════
    #  异步任务生命周期
    # ═══════════════════════════════════════════════════

    async def spawn(
        self,
        ctx: RequestContext,
        command: str,
        cwd: str | None = None,
        timeout: int | None = None,
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        创建并启动异步任务

        Returns:
            {task_id, command, pid, state}
        """
        timeout_ms = timeout or None  # spawn 默认不超时
        task_id = await self._do_spawn(command, cwd, env, timeout_ms)
        task = self._tasks[task_id]

        return {
            "task_id": task_id,
            "command": command,
            "pid": task.pid,
            "state": task.state.value,
        }

    async def stop(
        self,
        ctx: RequestContext,
        task_id: str,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        停止任务

        Args:
            task_id: 任务 ID
            force: True 强制终止（SIGKILL），False 优雅停止（发送中断信号，等待 5s 后强杀）
        """
        task = self._get_task(task_id)
        self._ensure_active(task)

        if force:
            force_kill(task.process)
            await self._safe_wait(task.process, 5.0)
            task.exit_code = task.process.returncode
            task.signal = "kill"
            self._complete_task(task, TaskState.KILLED)
        else:
            send_signal_by_name(task.process, "interrupt")
            exited = await self._safe_wait(task.process, 5.0)
            if not exited:
                force_kill(task.process)
                await self._safe_wait(task.process, 3.0)
            task.exit_code = task.process.returncode
            task.signal = "interrupt"
            self._complete_task(task, TaskState.STOPPED)

        # Windows: kill 后管道不自动关闭，取消 reader 避免 finalize 等 30s
        self._stream.cancel_readers(task.task_id)

        return task.to_dict()

    async def delete_task(
        self,
        ctx: RequestContext,
        task_id: str,
    ) -> dict[str, Any]:
        """
        删除已完成的任务，释放 Task 对象和输出缓冲区内存

        只能删除非运行中的任务（completed / failed / stopped / killed / timed_out）。
        运行中的任务需先 stop_task。
        """
        task = self._get_task(task_id)

        # 检测进程是否已自然退出
        await self._try_complete(task)

        if task.is_active:
            raise TaskAlreadyRunningError(
                f"任务仍在运行中，请先 stop_task: {task_id}",
                details={"task_id": task_id, "state": task.state.value},
            )

        # 清理流缓冲区
        if self._stream.has_task(task_id):
            await self._stream.finalize(task_id)
            self._stream.cleanup(task_id)

        # 取消超时监控
        monitor = self._timeout_tasks.pop(task_id, None)
        if monitor and not monitor.done():
            monitor.cancel()

        # 移除任务记录
        self._tasks.pop(task_id, None)

        return {
            "task_id": task_id,
            "deleted": True,
        }

    async def status(
        self,
        ctx: RequestContext,
        task_id: str,
    ) -> dict[str, Any]:
        """查询任务状态"""
        task = self._get_task(task_id)

        # 检测进程是否已自然退出（任务状态可能还是 RUNNING）
        await self._try_complete(task)

        result = task.to_dict()

        # 附加流信息
        if self._stream.has_task(task_id):
            result["stream"] = self._stream.summary(task_id)

        return result

    async def wait(
        self,
        ctx: RequestContext,
        task_id: str,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """
        等待任务完成

        Args:
            task_id: 任务 ID
            timeout: 超时毫秒数

        Returns:
            任务最终状态
        """
        task = self._get_task(task_id)

        if not task.is_active:
            return task.to_dict()

        timeout_s = (timeout or self.config.performance.default_timeout_ms) / 1000.0

        try:
            await asyncio.wait_for(task.process.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"等待任务超时: {task_id}",
                details={"task_id": task_id, "timeout_ms": timeout},
            )

        # 更新状态
        if task.is_active:
            exit_code = task.process.returncode
            task.exit_code = exit_code
            state = TaskState.COMPLETED if exit_code == 0 else TaskState.FAILED
            self._complete_task(task, state)

        return task.to_dict()

    async def list_tasks(
        self,
        ctx: RequestContext,
    ) -> dict[str, Any]:
        """列出所有任务"""
        tasks = [t.to_dict() for t in self._tasks.values()]
        active = sum(1 for t in self._tasks.values() if t.is_active)

        return {
            "tasks": tasks,
            "total": len(tasks),
            "active": active,
        }

    # ═══════════════════════════════════════════════════
    #  流式 I/O
    # ═══════════════════════════════════════════════════

    async def read_stdout(
        self,
        ctx: RequestContext,
        task_id: str,
        max_chars: int = 8192,
    ) -> dict[str, Any]:
        """
        读取标准输出（消费式）

        每次调用返回自上次调用以来的新输出。

        Returns:
            {task_id, output, eof}
        """
        self._get_task(task_id)  # 验证存在

        reader_id = task_id
        output = self._stream.read(task_id, "stdout", reader_id=reader_id, max_chars=max_chars)
        buf = self._stream.get_buffer(task_id, "stdout")

        return {
            "task_id": task_id,
            "output": output,
            "eof": buf.eof and not buf.has_unread(reader_id),
        }

    async def read_stderr(
        self,
        ctx: RequestContext,
        task_id: str,
        max_chars: int = 8192,
    ) -> dict[str, Any]:
        """读取标准错误（消费式）"""
        self._get_task(task_id)

        reader_id = task_id
        output = self._stream.read(task_id, "stderr", reader_id=reader_id, max_chars=max_chars)
        buf = self._stream.get_buffer(task_id, "stderr")

        return {
            "task_id": task_id,
            "output": output,
            "eof": buf.eof and not buf.has_unread(reader_id),
        }

    async def write_stdin(
        self,
        ctx: RequestContext,
        task_id: str,
        data: str,
        eof: bool = False,
    ) -> dict[str, Any]:
        """
        写入标准输入

        Args:
            task_id: 任务 ID
            data: 要写入的文本
            eof: 是否关闭 stdin（发送 EOF）
        """
        task = self._get_task(task_id)
        self._ensure_active(task)

        if task.process.stdin is None:
            raise InvalidParameterError(
                f"任务 stdin 不可用: {task_id}",
                details={"task_id": task_id},
            )

        if data:
            encoded_data, enc_used = encode_input(data)
            task.process.stdin.write(encoded_data)
            await task.process.stdin.drain()

        if eof:
            task.process.stdin.close()
            await task.process.stdin.wait_closed()

        return {
            "task_id": task_id,
            "written": len(data),
            "eof": eof,
        }

    # ═══════════════════════════════════════════════════
    #  内部方法
    # ═══════════════════════════════════════════════════

    async def _do_spawn(
        self,
        command: str,
        cwd: str | None,
        env: dict[str, str] | None,
        timeout_ms: int | None,
    ) -> str:
        """实际的进程创建逻辑"""
        # 并发限制检查
        active = sum(1 for t in self._tasks.values() if t.is_active)
        max_tasks = self.config.performance.max_concurrent_tasks
        if active >= max_tasks:
            raise MaxConcurrentTasksError(
                f"并发任务数已达上限: {active}/{max_tasks}",
                details={"active": active, "limit": max_tasks},
            )

        # 安全校验: 命令语法 + 黑名单
        if self._security:
            self._security.validate_command(command)

        # 安全校验: 工作目录
        work_dir = cwd or str(self.workspace)
        if cwd and self._security:
            resolved_cwd = self._security.validate_cwd(cwd, self.workspace)
            work_dir = str(resolved_cwd)

        # 安全校验: 环境变量
        if env and self._security:
            self._security.validate_env(env)

        shell = self._resolve_shell()
        if self._security:
            self._security.validate_shell(shell)

        task_id = uuid.uuid4().hex[:12]

        # 合并环境变量
        proc_env = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in _SAFE_ENV_KEYS
        }
        if env:
            proc_env.update(env)

        # 创建子进程
        creation_flags = get_subprocess_creation_flags()
        kwargs: dict[str, Any] = {
            "stdin": asyncio.subprocess.PIPE,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
            "cwd": work_dir,
            "env": proc_env,
            "executable": shell,
        }
        if creation_flags:
            kwargs["creationflags"] = creation_flags

        process = await asyncio.create_subprocess_shell(command, **kwargs)

        # 创建 Task
        now = datetime.now(timezone.utc)
        task = Task(
            task_id=task_id,
            command=command,
            cwd=work_dir,
            env=env,
            state=TaskState.RUNNING,
            process=process,
            pid=process.pid,
            created_at=now,
            started_at=now,
        )
        self._tasks[task_id] = task

        # 启动流管理
        self._stream.start(task_id, process)

        # 超时监控
        if timeout_ms:
            monitor = asyncio.create_task(self._timeout_monitor(task, timeout_ms))
            self._timeout_tasks[task_id] = monitor

        logger.info(
            "Task spawned: task_id=%s, command=%r, pid=%s",
            task_id, command, process.pid,
        )

        return task_id

    def _resolve_shell(self) -> str:
        """解析实际执行 shell，并确保其在当前平台可用。"""
        candidates = self.config.security.allowed_shells or [default_shell()]
        for shell in candidates:
            if Path(shell).is_absolute():
                if Path(shell).exists():
                    return shell
            else:
                resolved = shutil.which(shell)
                if resolved:
                    return resolved

        raise InvalidParameterError(
            "未找到可用 shell",
            details={"allowed_shells": candidates},
            suggestion="请检查 security.allowed_shells 配置或安装受支持的 shell",
        )

    async def _timeout_monitor(self, task: Task, timeout_ms: int) -> None:
        """超时监控协程"""
        try:
            await asyncio.sleep(timeout_ms / 1000.0)
            # 超时了，进程还在运行
            if task.is_active and task.process.returncode is None:
                logger.warning(
                    "Task timed out: task_id=%s, timeout=%dms",
                    task.task_id, timeout_ms,
                )
                force_kill(task.process)
                await self._safe_wait(task.process, 3.0)
                task.exit_code = task.process.returncode
                self._complete_task(task, TaskState.TIMED_OUT)
        except asyncio.CancelledError:
            pass  # 任务正常结束，monitor 被取消

    def _get_task(self, task_id: str) -> Task:
        """获取任务，不存在则抛异常"""
        task = self._tasks.get(task_id)
        if task is None:
            raise TaskNotFoundError(
                f"任务不存在: {task_id}",
                details={"task_id": task_id},
            )
        return task

    async def _try_complete(self, task: Task) -> None:
        """检测进程是否已自然退出，自动更新任务状态"""
        if not task.is_active:
            return
        if task.process.returncode is not None:
            # returncode 已收集
            exit_code = task.process.returncode
            task.exit_code = exit_code
            state = TaskState.COMPLETED if exit_code == 0 else TaskState.FAILED
            self._complete_task(task, state)
            return
        # 尝试非阻塞等待 — Windows 上 returncode 需要 wait() 才能收集
        try:
            await asyncio.wait_for(task.process.wait(), timeout=0.1)
            exit_code = task.process.returncode
            task.exit_code = exit_code
            state = TaskState.COMPLETED if exit_code == 0 else TaskState.FAILED
            self._complete_task(task, state)
        except asyncio.TimeoutError:
            pass  # 进程仍在运行

    @staticmethod
    def _ensure_active(task: Task) -> None:
        """确保任务处于活跃状态"""
        if not task.is_active:
            raise TaskNotFoundError(
                f"任务已结束: {task.task_id} (state={task.state.value})",
                details={"task_id": task.task_id, "state": task.state.value},
            )

    def _complete_task(self, task: Task, state: TaskState) -> None:
        """标记任务完成"""
        task.state = state
        task.completed_at = datetime.now(timezone.utc)

        # 取消超时监控
        monitor = self._timeout_tasks.pop(task.task_id, None)
        if monitor and not monitor.done():
            monitor.cancel()

    @staticmethod
    async def _safe_wait(
        process: asyncio.subprocess.Process, timeout: float
    ) -> bool:
        """安全等待进程退出，返回是否成功退出"""
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def cleanup_completed(self) -> int:
        """
        清理所有已完成任务的资源

        Returns:
            清理的任务数
        """
        completed = [
            tid for tid, t in self._tasks.items() if not t.is_active
        ]
        for tid in completed:
            if self._stream.has_task(tid):
                await self._stream.finalize(tid)
                self._stream.cleanup(tid)
            monitor = self._timeout_tasks.pop(tid, None)
            if monitor and not monitor.done():
                monitor.cancel()
            self._tasks.pop(tid, None)

        return len(completed)
