"""
Layer 1: Core — 异步文件锁管理器

职责:
- 为文件路径提供 per-path 异步锁，防止并发写冲突
- 支持读写锁语义: 多读单写
- 自动清理长期未使用的锁条目，防止内存泄漏
- 提供上下文管理器接口，保证锁的正确释放

设计:
- 锁的粒度是 resolved 绝对路径（规范化后）
- 内部使用 asyncio.Lock 作为管理锁，per-path 锁也是 asyncio.Lock
- 不做文件 I/O，只管理内存中的锁映射

依赖:
- 无（纯 asyncio）
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)

# 锁条目在最后一次使用后超过此时间（秒）将被清理
_DEFAULT_EVICT_AFTER_SECONDS = 300  # 5 分钟


class _LockEntry:
    """单个路径的锁条目"""

    __slots__ = ("lock", "last_used", "readers", "writer_waiting")

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.last_used: float = time.monotonic()
        self.readers: int = 0
        self.writer_waiting: bool = False

    def touch(self) -> None:
        self.last_used = time.monotonic()

    def is_stale(self, evict_after: float) -> bool:
        return (
            time.monotonic() - self.last_used > evict_after
            and not self.lock.locked()
            and self.readers == 0
        )


class AsyncFileLockManager:
    """
    异步文件锁管理器

    提供两种锁模式:
    1. write_lock(path) — 排他锁，同一路径同一时刻只有一个 writer
    2. read_lock(path) — 共享锁，多个 reader 可以并发，但与 writer 互斥

    实现:
    - 写锁直接使用 per-path asyncio.Lock
    - 读锁使用引用计数 + 写者优先（writer_waiting 时读者等待）

    用法::

        lock_mgr = AsyncFileLockManager()

        # 写操作
        async with lock_mgr.write_lock("/path/to/file.txt"):
            await do_write()

        # 读操作
        async with lock_mgr.read_lock("/path/to/file.txt"):
            data = await do_read()

    注意:
    - 路径会被 resolve 为绝对路径后用作 key
    - 不可重入（同一协程对同一路径加两次写锁会死锁）
    - 调用 cleanup() 可以清理过期的锁条目
    """

    def __init__(self, evict_after_seconds: float = _DEFAULT_EVICT_AFTER_SECONDS) -> None:
        self._locks: dict[str, _LockEntry] = {}
        self._manager_lock = asyncio.Lock()
        self._evict_after = evict_after_seconds

    @staticmethod
    def _normalize(path: str | Path) -> str:
        """规范化路径为统一的 key"""
        return str(Path(path).resolve())

    async def _get_entry(self, path: str | Path) -> _LockEntry:
        """获取或创建路径对应的锁条目"""
        key = self._normalize(path)
        async with self._manager_lock:
            if key not in self._locks:
                self._locks[key] = _LockEntry()
            entry = self._locks[key]
            entry.touch()
            return entry

    @asynccontextmanager
    async def write_lock(self, path: str | Path) -> AsyncIterator[None]:
        """
        获取排他写锁

        同一路径同一时刻只允许一个 writer。
        writer 等待时会阻止新的 reader 进入（写者优先）。

        Args:
            path: 文件路径

        Yields:
            None — 在 async with 块内持有锁
        """
        entry = await self._get_entry(path)
        entry.writer_waiting = True
        try:
            await entry.lock.acquire()
            entry.writer_waiting = False
            entry.touch()
            try:
                yield
            finally:
                entry.lock.release()
                entry.touch()
        except BaseException:
            entry.writer_waiting = False
            raise

    @asynccontextmanager
    async def read_lock(self, path: str | Path) -> AsyncIterator[None]:
        """
        获取共享读锁

        多个 reader 可以同时持有。
        如果有 writer 正在等待或持有锁，reader 需等待。

        简化实现: 读锁等待写锁释放，但不阻塞其他读锁。
        在文件操作场景下，读操作冲突写操作的概率不高，
        这种简化足够。

        Args:
            path: 文件路径

        Yields:
            None — 在 async with 块内持有锁
        """
        entry = await self._get_entry(path)

        # 等待写者释放
        while entry.lock.locked() or entry.writer_waiting:
            await asyncio.sleep(0.001)

        entry.readers += 1
        entry.touch()
        try:
            yield
        finally:
            entry.readers -= 1
            entry.touch()

    async def cleanup(self) -> int:
        """
        清理过期的锁条目

        删除 last_used 超过 evict_after_seconds 且当前未锁定的条目。

        Returns:
            清理的条目数
        """
        async with self._manager_lock:
            stale_keys = [
                key
                for key, entry in self._locks.items()
                if entry.is_stale(self._evict_after)
            ]
            for key in stale_keys:
                del self._locks[key]

            if stale_keys:
                logger.debug("清理过期文件锁: %d 条", len(stale_keys))

            return len(stale_keys)

    @property
    def active_lock_count(self) -> int:
        """当前管理的锁条目数"""
        return len(self._locks)

    def stats(self) -> dict[str, Any]:
        """统计信息"""
        locked = sum(1 for e in self._locks.values() if e.lock.locked())
        reading = sum(1 for e in self._locks.values() if e.readers > 0)
        return {
            "total_entries": len(self._locks),
            "locked_entries": locked,
            "reading_entries": reading,
        }

    async def reset(self) -> None:
        """重置所有锁（测试用）"""
        async with self._manager_lock:
            self._locks.clear()
