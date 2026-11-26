"""进程内 Trace 缓冲和默认采集器.

文件职责:
- 为调试接口提供最近若干 Trace 的内存查询.
- 限制 Trace 数量和每个 Trace 的事件数.
- 组合日志采集器和内存采集器.

核心边界:
这里不是持久化层; 结构化日志才是可长期保留的观测边界.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from threading import Lock
from typing import Any

from agent.observability.events import TraceEvent
from agent.observability.trace import (
    LoggingTraceCollector,
    TraceCollector,
)

logger = logging.getLogger(__name__)


class TraceBuffer:
    """有界的内存 Trace 缓冲区, 按 trace_id 保存事件列表."""

    def __init__(
        self,
        *,
        max_traces: int = 200,
        max_events_per_trace: int = 200,
    ) -> None:
        """初始化实例依赖."""
        self.max_traces = max_traces
        self.max_events_per_trace = max_events_per_trace
        # OrderedDict 用来在超出容量时淘汰最旧 Trace.
        self._events: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
        self._lock = Lock()

    def add(self, event: TraceEvent) -> None:
        """追加事件; 超出单 Trace 或总 Trace 上限时淘汰最旧数据."""
        payload = event.as_dict()
        with self._lock:
            events = self._events.setdefault(event.trace_id, [])
            events.append(payload)
            if len(events) > self.max_events_per_trace:
                del events[: len(events) - self.max_events_per_trace]
            self._events.move_to_end(event.trace_id)
            while len(self._events) > self.max_traces:
                self._events.popitem(last=False)

    def get(self, trace_id: str) -> list[dict[str, Any]]:
        """返回指定 Trace 的事件副本."""
        with self._lock:
            return list(self._events.get(trace_id, []))

    def clear(self) -> None:
        """清空缓冲区, 主要供测试使用."""
        with self._lock:
            self._events.clear()


class BufferTraceCollector:
    """把事件写入 TraceBuffer 的采集器."""

    def __init__(self, buffer: TraceBuffer) -> None:
        """初始化实例依赖."""
        self.buffer = buffer

    def emit(self, event: TraceEvent) -> None:
        """写入内存缓冲."""
        self.buffer.add(event)


class CompositeTraceCollector:
    """把事件分发给多个 Collector, 单个 sink 失败不影响其他 sink."""

    def __init__(self, *collectors: TraceCollector) -> None:
        """初始化实例依赖."""
        self.collectors = collectors

    def emit(self, event: TraceEvent) -> None:
        """逐个调用 sink, 记录但不传播异常."""
        for collector in self.collectors:
            try:
                collector.emit(event)
            except Exception as exc:
                logger.debug("agent_trace_sink_failed", exc_info=exc)
                continue


# 进程级单例; 由 API 调试接口读取.
_TRACE_BUFFER = TraceBuffer()
_DEFAULT_COLLECTOR: TraceCollector | None = None


def get_trace_buffer() -> TraceBuffer:
    """返回进程内 Trace 缓冲."""
    return _TRACE_BUFFER


def get_default_trace_collector() -> TraceCollector:
    """懒加载默认采集器: 同时写日志和内存."""
    global _DEFAULT_COLLECTOR
    if _DEFAULT_COLLECTOR is None:
        _DEFAULT_COLLECTOR = CompositeTraceCollector(
            LoggingTraceCollector(),
            BufferTraceCollector(_TRACE_BUFFER),
        )
    return _DEFAULT_COLLECTOR
