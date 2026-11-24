"""Bounded process-local trace store and default collectors.

This is intentionally not a database or Redis persistence layer. It provides a
minimal query surface for a single-process debug endpoint; the structured log
line remains the durable observability boundary.
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
    """Bounded in-memory trace buffer with per-trace event caps."""

    def __init__(
        self,
        *,
        max_traces: int = 200,
        max_events_per_trace: int = 200,
    ) -> None:
        self.max_traces = max_traces
        self.max_events_per_trace = max_events_per_trace
        self._events: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
        self._lock = Lock()

    def add(self, event: TraceEvent) -> None:
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
        with self._lock:
            return list(self._events.get(trace_id, []))

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


class BufferTraceCollector:
    def __init__(self, buffer: TraceBuffer) -> None:
        self.buffer = buffer

    def emit(self, event: TraceEvent) -> None:
        self.buffer.add(event)


class CompositeTraceCollector:
    """Fan out to collectors while isolating failures per sink."""

    def __init__(self, *collectors: TraceCollector) -> None:
        self.collectors = collectors

    def emit(self, event: TraceEvent) -> None:
        for collector in self.collectors:
            try:
                collector.emit(event)
            except Exception as exc:
                logger.debug("agent_trace_sink_failed", exc_info=exc)
                continue


_TRACE_BUFFER = TraceBuffer()
_DEFAULT_COLLECTOR: TraceCollector | None = None


def get_trace_buffer() -> TraceBuffer:
    return _TRACE_BUFFER


def get_default_trace_collector() -> TraceCollector:
    global _DEFAULT_COLLECTOR
    if _DEFAULT_COLLECTOR is None:
        _DEFAULT_COLLECTOR = CompositeTraceCollector(
            LoggingTraceCollector(),
            BufferTraceCollector(_TRACE_BUFFER),
        )
    return _DEFAULT_COLLECTOR
