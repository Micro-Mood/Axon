"""
Layer 3: Stream — 流生命周期管理器

管理所有活跃进程的输出流。

职责:
- 为每个进程创建 stdout/stderr 的 OutputBuffer
- 启动 reader 协程持续从进程管道读取数据（4KB 块）
- 提供统一的 read/drain/peek 接口
- 管理流的生命周期: start → (read/drain) → finalize → cleanup

依赖:
- mcp.stream.buffer.OutputBuffer
- mcp.core.errors.TaskNotFoundError
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from ..core.errors import TaskNotFoundError
from .buffer import OutputBuffer

logger = logging.getLogger(__name__)

# reader 协程每次从管道读取的块大小
_READ_CHUNK_SIZE = 4096


# ═══════════════════════════════════════════════════════
#  内部数据结构
# ═══════════════════════════════════════════════════════

@dataclass
class _TaskStreams:
    """一个进程的所有输出流"""
    stdout: OutputBuffer
    stderr: OutputBuffer
    # 关联的 reader 协程（用于 finalize 时等待）
    reader_tasks: list[asyncio.Task] = field(default_factory=list)


# ═══════════════════════════════════════════════════════
#  StreamManager
# ═══════════════════════════════════════════════════════

class StreamManager:
    """
    流生命周期管理器

    每个 task_id 对应一组流（stdout + stderr）。
    start() 启动后台 reader 协程，持续从进程管道读数据到 OutputBuffer。
    finalize() 等待 reader 协程结束（确保数据全部读完），返回最终输出。
    cleanup() 释放缓冲区内存。

    典型生命周期:
        mgr.start(task_id, process)         # 进程启动时
        mgr.read(task_id, "stdout")         # 实时读取（可选）
        result = await mgr.finalize(task_id) # 进程退出后
        mgr.cleanup(task_id)                 # 不再需要时
    """

    def __init__(self, max_buffer_size: int = 10 * 1024 * 1024):
        """
        Args:
            max_buffer_size: 每个流的最大缓冲字节数，默认 10MB
        """
        self._max_buffer_size = max_buffer_size
        self._streams: dict[str, _TaskStreams] = {}

    # ═══════════════════════════════════════════════════
    #  生命周期
    # ═══════════════════════════════════════════════════

    def start(self, task_id: str, process: asyncio.subprocess.Process) -> None:
        """
        开始读取进程输出

        创建 stdout/stderr 的 OutputBuffer，启动 reader 协程。

        Args:
            task_id: 任务唯一标识
            process: asyncio 子进程对象（stdout/stderr 必须是 PIPE）
        """
        if task_id in self._streams:
            logger.warning("StreamManager: task_id %s 已存在，将覆盖", task_id)
            # 取消旧的 reader 协程
            self._cancel_readers(task_id)

        stdout_buf = OutputBuffer("stdout", max_size=self._max_buffer_size)
        stderr_buf = OutputBuffer("stderr", max_size=self._max_buffer_size)

        reader_tasks: list[asyncio.Task] = []

        # 启动 stdout reader
        if process.stdout is not None:
            task = asyncio.create_task(
                self._read_loop(process.stdout, stdout_buf),
                name=f"stream-reader-{task_id}-stdout",
            )
            reader_tasks.append(task)
        else:
            stdout_buf.mark_eof()

        # 启动 stderr reader
        if process.stderr is not None:
            task = asyncio.create_task(
                self._read_loop(process.stderr, stderr_buf),
                name=f"stream-reader-{task_id}-stderr",
            )
            reader_tasks.append(task)
        else:
            stderr_buf.mark_eof()

        self._streams[task_id] = _TaskStreams(
            stdout=stdout_buf,
            stderr=stderr_buf,
            reader_tasks=reader_tasks,
        )

        logger.debug(
            "StreamManager: 开始读取 task=%s (stdout=%s, stderr=%s)",
            task_id,
            process.stdout is not None,
            process.stderr is not None,
        )

    async def finalize(self, task_id: str) -> dict[str, Any]:
        """
        进程结束后收尾

        等待所有 reader 协程结束（确保管道数据全部读完），
        然后返回最终输出。

        Args:
            task_id: 任务唯一标识

        Returns:
            {
                "stdout": str,          # 全部标准输出文本
                "stderr": str,          # 全部标准错误文本
                "stdout_raw_b64": str,  # stdout 原始字节 base64
                "stderr_raw_b64": str,  # stderr 原始字节 base64
                "stdout_summary": dict, # stdout 缓冲区摘要
                "stderr_summary": dict, # stderr 缓冲区摘要
            }

        Raises:
            TaskNotFoundError: task_id 不存在
        """
        streams = self._get_streams(task_id)

        # 等待所有 reader 协程完成（最多等 30 秒）
        if streams.reader_tasks:
            done, pending = await asyncio.wait(
                streams.reader_tasks,
                timeout=30.0,
            )
            # 超时的 reader 强制取消
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            if pending:
                logger.warning(
                    "StreamManager: task=%s 有 %d 个 reader 超时被取消",
                    task_id,
                    len(pending),
                )

        # 确保 eof 标记
        if not streams.stdout.eof:
            streams.stdout.mark_eof()
        if not streams.stderr.eof:
            streams.stderr.mark_eof()

        return {
            "stdout": streams.stdout.get_all(),
            "stderr": streams.stderr.get_all(),
            "stdout_raw_b64": streams.stdout.get_raw_base64(),
            "stderr_raw_b64": streams.stderr.get_raw_base64(),
            "stdout_summary": streams.stdout.summary(),
            "stderr_summary": streams.stderr.summary(),
        }

    def cleanup(self, task_id: str) -> None:
        """
        释放缓冲区内存

        调用后该 task_id 的所有数据不可再访问。

        Args:
            task_id: 任务唯一标识（不存在则静默忽略）
        """
        self._cancel_readers(task_id)
        removed = self._streams.pop(task_id, None)
        if removed:
            logger.debug("StreamManager: 清理 task=%s", task_id)

    # ═══════════════════════════════════════════════════
    #  读取接口
    # ═══════════════════════════════════════════════════

    def get_buffer(self, task_id: str, stream: str) -> OutputBuffer:
        """
        获取指定流的 OutputBuffer

        Args:
            task_id: 任务唯一标识
            stream: "stdout" 或 "stderr"

        Returns:
            OutputBuffer 实例

        Raises:
            TaskNotFoundError: task_id 不存在
            ValueError: stream 不是 "stdout" 或 "stderr"
        """
        streams = self._get_streams(task_id)
        if stream == "stdout":
            return streams.stdout
        elif stream == "stderr":
            return streams.stderr
        else:
            raise ValueError(f"无效的流名称: {stream!r}，必须是 'stdout' 或 'stderr'")

    def read(
        self,
        task_id: str,
        stream: str,
        reader_id: str = "default",
        max_chars: int = 8192,
    ) -> str:
        """
        消费式读取指定流

        Args:
            task_id: 任务标识
            stream: "stdout" 或 "stderr"
            reader_id: 消费者标识
            max_chars: 最多返回字符数

        Returns:
            文本内容
        """
        return self.get_buffer(task_id, stream).read(reader_id, max_chars)

    def drain(
        self,
        task_id: str,
        stream: str,
        reader_id: str = "default",
    ) -> str:
        """
        读取指定流的全部剩余内容

        Args:
            task_id: 任务标识
            stream: "stdout" 或 "stderr"
            reader_id: 消费者标识

        Returns:
            全部剩余文本
        """
        return self.get_buffer(task_id, stream).drain(reader_id)

    def peek(
        self,
        task_id: str,
        stream: str,
        max_chars: int = 8192,
    ) -> str:
        """
        非破坏性读取指定流

        Args:
            task_id: 任务标识
            stream: "stdout" 或 "stderr"
            max_chars: 最多返回字符数

        Returns:
            缓冲区头部文本（不移动游标）
        """
        return self.get_buffer(task_id, stream).peek(max_chars)

    def peek_tail(
        self,
        task_id: str,
        stream: str,
        max_chars: int = 8192,
    ) -> str:
        """
        非破坏性读取指定流尾部

        Args:
            task_id: 任务标识
            stream: "stdout" 或 "stderr"
            max_chars: 最多返回字符数

        Returns:
            缓冲区尾部文本（不移动游标）
        """
        return self.get_buffer(task_id, stream).peek_tail(max_chars)

    # ═══════════════════════════════════════════════════
    #  状态查询
    # ═══════════════════════════════════════════════════

    def has_task(self, task_id: str) -> bool:
        """检查 task_id 是否存在"""
        return task_id in self._streams

    def list_tasks(self) -> list[str]:
        """返回所有活跃的 task_id"""
        return list(self._streams.keys())

    def summary(self, task_id: str) -> dict[str, Any]:
        """
        获取指定任务的流状态摘要

        Args:
            task_id: 任务标识

        Returns:
            {
                "task_id": str,
                "stdout": OutputBuffer.summary(),
                "stderr": OutputBuffer.summary(),
                "readers_active": int,
            }
        """
        streams = self._get_streams(task_id)
        active_readers = sum(
            1 for t in streams.reader_tasks if not t.done()
        )
        return {
            "task_id": task_id,
            "stdout": streams.stdout.summary(),
            "stderr": streams.stderr.summary(),
            "readers_active": active_readers,
        }

    def global_stats(self) -> dict[str, Any]:
        """
        全局统计信息

        Returns:
            {
                "active_tasks": int,
                "total_bytes_buffered": int,
                "total_bytes_received": int,
                "tasks": [task_id, ...],
            }
        """
        total_buffered = 0
        total_received = 0
        for streams in self._streams.values():
            total_buffered += streams.stdout.size + streams.stderr.size
            total_received += streams.stdout.total_received + streams.stderr.total_received

        return {
            "active_tasks": len(self._streams),
            "total_bytes_buffered": total_buffered,
            "total_bytes_received": total_received,
            "tasks": list(self._streams.keys()),
        }

    # ═══════════════════════════════════════════════════
    #  内部方法
    # ═══════════════════════════════════════════════════

    def _get_streams(self, task_id: str) -> _TaskStreams:
        """获取流集合，不存在则抛异常"""
        streams = self._streams.get(task_id)
        if streams is None:
            raise TaskNotFoundError(
                f"任务不存在: {task_id}",
                details={"task_id": task_id},
            )
        return streams

    def _cancel_readers(self, task_id: str) -> None:
        """取消指定任务的所有 reader 协程"""
        streams = self._streams.get(task_id)
        if streams is None:
            return
        for task in streams.reader_tasks:
            if not task.done():
                task.cancel()

    @staticmethod
    async def _read_loop(
        pipe: asyncio.StreamReader,
        buffer: OutputBuffer,
    ) -> None:
        """
        reader 协程: 持续从管道读数据到 buffer

        循环逻辑:
        1. 每次读 4KB
        2. 空数据 = EOF → 退出
        3. 写入 buffer（自动解码 + 截断保护）
        4. 管道关闭/异常 → 退出

        Args:
            pipe: 进程的 stdout 或 stderr StreamReader
            buffer: 写入目标缓冲区
        """
        try:
            while True:
                try:
                    chunk = await pipe.read(_READ_CHUNK_SIZE)
                except (ConnectionError, OSError):
                    # 管道断开
                    break

                if not chunk:
                    # EOF
                    break

                buffer.write(chunk)

                # 已截断 → 不再读了，剩余数据让进程自行丢弃
                # 但不 break — 还需要等 EOF 才能让 process.wait() 正常返回
                # 读取但不写入（buffer.write 会返回 0）
        except asyncio.CancelledError:
            # 被外部取消（如 finalize 超时）
            pass
        except Exception as e:
            logger.error(
                "StreamManager: reader 异常 (%s): %s",
                buffer.name,
                e,
            )
        finally:
            buffer.mark_eof()
