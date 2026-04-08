"""
Layer 3: Stream — 输出缓冲区

每个进程的每个流（stdout/stderr）对应一个 OutputBuffer 实例。

特性:
- 写入时自动解码（通过 platform.decode_output）
- 硬性大小限制，超限自动截断（不会 OOM）
- 支持多消费者（每个 reader 维护独立游标）
- 消费式读取 read() + 非破坏性 peek() + 全量 drain()
- 读过的数据不删除（与 AutomateX 的区别），多消费者各自独立

依赖:
- mcp.platform.decode_output (编码解码)
"""

from __future__ import annotations

import base64
import threading
from dataclasses import dataclass, field

from ..platform import decode_output


# ═══════════════════════════════════════════════════════
#  OutputBuffer
# ═══════════════════════════════════════════════════════

class OutputBuffer:
    """
    统一输出缓冲区

    线程安全: 写入端和读取端可以在不同线程/协程中操作。
    通过 threading.Lock 保护共享状态。

    容量限制:
    - max_size 限制 _raw 的字节数
    - 超限后新数据被丢弃，_truncated 置 True
    - total_received 始终累加（用于统计实际产出量）
    """

    __slots__ = (
        "_name",
        "_max_size",
        "_raw",
        "_decoded",
        "_total_received",
        "_truncated",
        "_eof",
        "_readers",
        "_encoding_used",
        "_lock",
    )

    def __init__(self, name: str, max_size: int = 10 * 1024 * 1024):
        """
        Args:
            name: 流名称，"stdout" 或 "stderr"
            max_size: 最大缓冲字节数，默认 10MB
        """
        self._name: str = name
        self._max_size: int = max_size

        # 数据存储
        self._raw: bytearray = bytearray()
        self._decoded: str = ""

        # 状态
        self._total_received: int = 0
        self._truncated: bool = False
        self._eof: bool = False

        # 记录使用过的编码（最后一次解码使用的）
        self._encoding_used: str = "utf-8"

        # 多消费者游标: reader_id → 已读字符位置
        self._readers: dict[str, int] = {}

        # 线程安全锁
        self._lock = threading.Lock()

    # ═══════════════════════════════════════════════════
    #  写入端
    # ═══════════════════════════════════════════════════

    def write(self, data: bytes) -> int:
        """
        写入原始字节数据

        流程:
        1. 累计 total_received += len(data)
        2. 已截断 → 丢弃，返回 0
        3. 检查剩余空间:
           a. 完全放得下 → 全部写入
           b. 放不下 → 写入能放下的部分，标记截断
        4. 追加到 _raw
        5. 调 platform.decode_output() 解码
        6. 追加到 _decoded

        Args:
            data: 原始字节

        Returns:
            实际写入的字节数（0 表示已截断，全部丢弃）
        """
        if not data:
            return 0

        with self._lock:
            data_len = len(data)
            self._total_received += data_len

            # 已截断 → 后续数据全部丢弃
            if self._truncated:
                return 0

            # 计算剩余空间
            remaining = self._max_size - len(self._raw)
            if remaining <= 0:
                self._truncated = True
                return 0

            # 部分截断: 只写入能放下的部分
            if data_len > remaining:
                data = data[:remaining]
                self._truncated = True

            actual_len = len(data)

            # 追加原始字节
            self._raw.extend(data)

            # 解码并追加
            text, encoding = decode_output(data)
            self._decoded += text
            self._encoding_used = encoding

            return actual_len

    def mark_eof(self) -> None:
        """标记流结束（进程管道关闭）"""
        with self._lock:
            self._eof = True

    # ═══════════════════════════════════════════════════
    #  读取端 — 消费式
    # ═══════════════════════════════════════════════════

    def read(self, reader_id: str = "default", max_chars: int = 8192) -> str:
        """
        消费式读取

        每个 reader_id 维护独立游标。
        读过的内容不从 buffer 中删除。
        多个消费者可以各自独立消费。

        Args:
            reader_id: 消费者标识，不同消费者互不干扰
            max_chars: 最多返回的字符数

        Returns:
            最多 max_chars 个字符的文本。
            空字符串表示当前无新内容（可能还没写入，也可能已读完）。
        """
        with self._lock:
            pos = self._readers.get(reader_id, 0)
            end = min(pos + max_chars, len(self._decoded))
            chunk = self._decoded[pos:end]
            self._readers[reader_id] = end
            return chunk

    def drain(self, reader_id: str = "default") -> str:
        """
        读取指定消费者的全部剩余内容

        将游标移到末尾。

        Args:
            reader_id: 消费者标识

        Returns:
            从游标位置到末尾的全部文本
        """
        with self._lock:
            pos = self._readers.get(reader_id, 0)
            chunk = self._decoded[pos:]
            self._readers[reader_id] = len(self._decoded)
            return chunk

    # ═══════════════════════════════════════════════════
    #  读取端 — 非破坏性
    # ═══════════════════════════════════════════════════

    def peek(self, max_chars: int = 8192) -> str:
        """
        非破坏性读取（不移动任何游标）

        从头开始返回最多 max_chars 个字符。

        Args:
            max_chars: 最多返回的字符数

        Returns:
            缓冲区头部的文本
        """
        with self._lock:
            return self._decoded[:max_chars]

    def peek_tail(self, max_chars: int = 8192) -> str:
        """
        非破坏性读取尾部（不移动任何游标）

        返回缓冲区最后 max_chars 个字符。
        用于查看最新输出。

        Args:
            max_chars: 最多返回的字符数

        Returns:
            缓冲区尾部的文本
        """
        with self._lock:
            if len(self._decoded) <= max_chars:
                return self._decoded
            return self._decoded[-max_chars:]

    def get_all(self) -> str:
        """
        获取全部已解码内容（忽略游标）

        Returns:
            缓冲区中的全部文本
        """
        with self._lock:
            return self._decoded

    def get_raw(self) -> bytes:
        """
        获取原始字节数据的副本

        Returns:
            原始字节的 bytes 对象（副本，不是引用）
        """
        with self._lock:
            return bytes(self._raw)

    def get_raw_base64(self) -> str:
        """
        获取原始字节的 base64 编码

        用于在 JSON 中传输二进制数据。

        Returns:
            base64 编码字符串
        """
        with self._lock:
            return base64.b64encode(bytes(self._raw)).decode("ascii")

    # ═══════════════════════════════════════════════════
    #  消费者管理
    # ═══════════════════════════════════════════════════

    def register_reader(self, reader_id: str, from_beginning: bool = False) -> None:
        """
        注册一个新消费者

        Args:
            reader_id: 消费者标识
            from_beginning: True 从头开始，False 从当前末尾开始（只看新内容）
        """
        with self._lock:
            if from_beginning:
                self._readers[reader_id] = 0
            else:
                self._readers[reader_id] = len(self._decoded)

    def unregister_reader(self, reader_id: str) -> None:
        """
        注销消费者，释放游标

        Args:
            reader_id: 消费者标识
        """
        with self._lock:
            self._readers.pop(reader_id, None)

    def reset_reader(self, reader_id: str) -> None:
        """
        重置消费者游标到开头

        Args:
            reader_id: 消费者标识
        """
        with self._lock:
            self._readers[reader_id] = 0

    # ═══════════════════════════════════════════════════
    #  状态查询
    # ═══════════════════════════════════════════════════

    @property
    def name(self) -> str:
        """流名称"""
        return self._name

    @property
    def eof(self) -> bool:
        """流是否已结束"""
        return self._eof

    @property
    def truncated(self) -> bool:
        """是否已触发截断"""
        return self._truncated

    @property
    def size(self) -> int:
        """当前缓冲区字节数"""
        with self._lock:
            return len(self._raw)

    @property
    def char_count(self) -> int:
        """当前缓冲区字符数"""
        with self._lock:
            return len(self._decoded)

    @property
    def total_received(self) -> int:
        """累计接收字节数（含截断丢弃的）"""
        return self._total_received

    @property
    def encoding_used(self) -> str:
        """最后一次解码使用的编码"""
        return self._encoding_used

    def unread_count(self, reader_id: str = "default") -> int:
        """
        指定消费者还有多少字符未读

        Args:
            reader_id: 消费者标识

        Returns:
            未读字符数
        """
        with self._lock:
            pos = self._readers.get(reader_id, 0)
            return len(self._decoded) - pos

    def has_unread(self, reader_id: str = "default") -> bool:
        """
        指定消费者是否有未读内容

        Args:
            reader_id: 消费者标识

        Returns:
            True 有未读内容
        """
        return self.unread_count(reader_id) > 0

    def summary(self) -> dict:
        """
        返回缓冲区状态摘要

        Returns:
            {
                "name": "stdout",
                "size_bytes": 12345,
                "char_count": 12000,
                "total_received": 15000,
                "truncated": False,
                "eof": True,
                "encoding": "utf-8",
                "readers": {"default": {"position": 5000, "unread": 7000}},
            }
        """
        with self._lock:
            readers_info = {}
            for rid, pos in self._readers.items():
                readers_info[rid] = {
                    "position": pos,
                    "unread": len(self._decoded) - pos,
                }

            return {
                "name": self._name,
                "size_bytes": len(self._raw),
                "char_count": len(self._decoded),
                "total_received": self._total_received,
                "truncated": self._truncated,
                "eof": self._eof,
                "encoding": self._encoding_used,
                "readers": readers_info,
            }

    def __repr__(self) -> str:
        return (
            f"OutputBuffer({self._name!r}, "
            f"size={len(self._raw)}, "
            f"chars={len(self._decoded)}, "
            f"eof={self._eof}, "
            f"truncated={self._truncated})"
        )
