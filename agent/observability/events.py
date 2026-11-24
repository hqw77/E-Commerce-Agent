"""Structured Agent execution trace events."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

TraceStatus = Literal["STARTED", "SUCCESS", "ERROR", "EMPTY", "SKIPPED"]
RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]


@dataclass(frozen=True, slots=True)
class TraceEvent:
    """One immutable event in one Agent request trace.

    The event is deliberately broad enough to represent runtime, graph node,
    route, RAG, Tool and conversation steps without coupling the trace module
    to LangGraph or SQLAlchemy.
    """

    trace_id: str
    request_id: str
    conversation_id: str
    user_id: int
    event_type: str
    node_name: str | None
    intent: str | None
    route: str | None
    tool_name: str | None
    arguments_summary: dict[str, Any] | None
    risk_level: str | None
    execution_status: str
    duration_ms: float | None
    result_summary: dict[str, Any] | None
    error_code: str | None
    timestamp: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
