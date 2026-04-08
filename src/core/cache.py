"""
Layer 1: Core — 多桶 TTL 缓存

特性:
- 多个独立缓存桶（metadata, directory, search, task）
- 每桶独立 TTL 和容量限制
- LRU 淘汰（满时踢最久未访问的）
- 命中率统计
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _CacheEntry:
    """缓存条目"""
    value: Any
    expires_at: float  # time.monotonic() 时间戳


@dataclass
class _BucketStats:
    """桶统计"""
    hits: int = 0
    misses: int = 0
    evictions: int = 0


# 默认桶定义
DEFAULT_BUCKETS: dict[str, dict[str, int]] = {
    "metadata": {"ttl": 60, "max_size": 1000},
    "directory": {"ttl": 30, "max_size": 200},
    "search": {"ttl": 300, "max_size": 100},
    "task": {"ttl": 10, "max_size": 50},
}


class CacheManager:
    """多桶 TTL 缓存"""

    def __init__(self, buckets: dict[str, dict[str, int]] | None = None):
        """
        Args:
            buckets: 桶定义，格式 {"name": {"ttl": 秒, "max_size": 条数}}
                     None 使用默认桶
        """
        bucket_defs = buckets or DEFAULT_BUCKETS
        self._buckets: dict[str, OrderedDict[str, _CacheEntry]] = {}
        self._bucket_config: dict[str, dict[str, int]] = {}
        self._stats: dict[str, _BucketStats] = {}

        for name, cfg in bucket_defs.items():
            self._buckets[name] = OrderedDict()
            self._bucket_config[name] = cfg
            self._stats[name] = _BucketStats()

    def _get_bucket(self, bucket: str) -> OrderedDict[str, _CacheEntry]:
        """获取桶，不存在则 KeyError"""
        try:
            return self._buckets[bucket]
        except KeyError:
            raise KeyError(f"缓存桶不存在: {bucket}")

    def _is_expired(self, entry: _CacheEntry) -> bool:
        return time.monotonic() > entry.expires_at

    # ── 读写 ──

    def get(self, bucket: str, key: str) -> Any | None:
        """
        获取缓存值

        Returns:
            缓存值，不存在或过期返回 None
        """
        b = self._get_bucket(bucket)
        entry = b.get(key)

        if entry is None:
            self._stats[bucket].misses += 1
            return None

        if self._is_expired(entry):
            del b[key]
            self._stats[bucket].misses += 1
            return None

        # LRU: 移到末尾（最近访问）
        b.move_to_end(key)
        self._stats[bucket].hits += 1
        return entry.value

    def set(self, bucket: str, key: str, value: Any) -> None:
        """写入缓存"""
        b = self._get_bucket(bucket)
        cfg = self._bucket_config[bucket]
        ttl = cfg["ttl"]
        max_size = cfg["max_size"]

        # 已存在则更新
        if key in b:
            b[key] = _CacheEntry(value=value, expires_at=time.monotonic() + ttl)
            b.move_to_end(key)
            return

        # 容量满 → 淘汰最旧（OrderedDict 头部）
        while len(b) >= max_size:
            b.popitem(last=False)
            self._stats[bucket].evictions += 1

        b[key] = _CacheEntry(value=value, expires_at=time.monotonic() + ttl)

    # ── 失效 ──

    def invalidate(self, bucket: str, key: str) -> None:
        """使指定 key 失效"""
        b = self._get_bucket(bucket)
        b.pop(key, None)

    def invalidate_prefix(self, bucket: str, prefix: str) -> None:
        """使指定前缀的所有 key 失效"""
        b = self._get_bucket(bucket)
        keys_to_remove = [k for k in b if k.startswith(prefix)]
        for k in keys_to_remove:
            del b[k]

    def clear(self, bucket: str | None = None) -> None:
        """
        清空缓存

        Args:
            bucket: 指定桶名，None 清空全部
        """
        if bucket is not None:
            self._get_bucket(bucket).clear()
        else:
            for b in self._buckets.values():
                b.clear()

    # ── 统计 ──

    def stats(self) -> dict[str, dict]:
        """返回各桶统计信息"""
        result = {}
        for name, s in self._stats.items():
            total = s.hits + s.misses
            result[name] = {
                "size": len(self._buckets[name]),
                "max_size": self._bucket_config[name]["max_size"],
                "ttl": self._bucket_config[name]["ttl"],
                "hits": s.hits,
                "misses": s.misses,
                "hit_rate": round(s.hits / total, 3) if total > 0 else 0.0,
                "evictions": s.evictions,
            }
        return result
