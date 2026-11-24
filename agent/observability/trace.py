"""Trace collection boundaries for Agent execution."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from app.core.logging import get_logger

from agent.observability.events import TraceEvent
from agent.observability.redaction import redact_payload


class TraceCollector(Protocol):
    """A side-effect boundary; a collector must never break Agent execution."""

    def emit(self, event: TraceEvent) -> None: ...


class NoopTraceCollector:
    """Default collector used by unit tests and when tracing is disabled."""

    def emit(self, event: TraceEvent) -> None:
        return None


class LoggingTraceCollector:
    """Emit one structured log line per trace event using existing structlog."""

    def __init__(self, logger: Any | None = None) -> None:
        self._logger = logger or get_logger("agent.trace")

    def emit(self, event: TraceEvent) -> None:
        self._logger.info("agent_trace_event", **event.as_dict())


class TraceRecorder:
    """Request-scoped trace builder.

    All payloads are defensively redacted here, even if callers already
    attempted to summarize them. Collector failures are swallowed; tracing is
    observability only and must never change business behavior.
    """

    __slots__ = (
        "collector",
        "conversation_id",
        "request_id",
        "trace_id",
        "user_id",
    )

    def __init__(
        self,
        *,
        trace_id: str,
        request_id: str,
        conversation_id: str,
        user_id: int,
        collector: TraceCollector | None = None,
    ) -> None:
        self.trace_id = trace_id
        self.request_id = request_id
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.collector = collector or NoopTraceCollector()

    def emit(
        self,
        event_type: str,
        *,
        node_name: str | None = None,
        intent: str | None = None,
        route: str | None = None,
        tool_name: str | None = None,
        arguments_summary: dict[str, Any] | None = None,
        risk_level: str | None = None,
        execution_status: str = "SUCCESS",
        duration_ms: float | None = None,
        result_summary: dict[str, Any] | None = None,
        error_code: str | None = None,
    ) -> None:
        event = TraceEvent(
            trace_id=self.trace_id,
            request_id=self.request_id,
            conversation_id=self.conversation_id,
            user_id=self.user_id,
            event_type=event_type,
            node_name=node_name,
            intent=intent,
            route=route,
            tool_name=tool_name,
            arguments_summary=(
                redact_payload(arguments_summary)
                if arguments_summary is not None
                else None
            ),
            risk_level=risk_level,
            execution_status=execution_status,
            duration_ms=duration_ms,
            result_summary=(
                redact_payload(result_summary)
                if result_summary is not None
                else None
            ),
            error_code=error_code,
            timestamp=datetime.now(UTC).isoformat(),
        )
        try:
            self.collector.emit(event)
        except Exception:  # noqa: BLE001 - tracing must be best-effort
            # Observability is best-effort. A broken sink must not break chat.
            return
