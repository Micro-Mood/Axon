"""
Layer 3: Stream — 流管理层

提供: OutputBuffer (单流缓冲区) + StreamManager (多任务流生命周期管理)

依赖:
- Layer 1: core.errors (TaskNotFoundError)
- Layer 2: platform (decode_output)
"""

from .buffer import OutputBuffer
from .manager import StreamManager

__all__ = [
    "OutputBuffer",
    "StreamManager",
]
