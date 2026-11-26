"""Agent Trace 采集边界.

文件职责:
- 定义 Collector 协议和默认 Noop/Logging 实现.
- 在 TraceRecorder 中统一构造事件并脱敏.
- 保证采集失败不影响 Agent 主流程.

核心边界:
Trace 是 best-effort 观测, 不是业务状态或审计的唯一来源.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from app.core.logging import get_logger

from agent.observability.events import TraceEvent
from agent.observability.redaction import redact_payload


class TraceCollector(Protocol):
    """Trace 采集器的副作用边界; emit 不应影响主流程."""

    def emit(self, event: TraceEvent) -> None:
        """发送一条 Trace 事件."""
        ...


class NoopTraceCollector:
    """关闭 Trace 或单元测试时使用的空采集器."""

    def emit(self, event: TraceEvent) -> None:
        """丢弃事件."""
        return None  # noqa: RET501 - keep the explicit protocol implementation


class LoggingTraceCollector:
    """把每个事件写成一条 structlog 结构化日志."""

    def __init__(self, logger: Any | None = None) -> None:
        """初始化实例依赖."""
        self._logger = logger or get_logger("agent.trace")

    def emit(self, event: TraceEvent) -> None:
        """输出 agent_trace_event 日志."""
        self._logger.info("agent_trace_event", **event.as_dict())


class TraceRecorder:
    """请求级 Trace 构造器.

    所有参数和结果在这里再次脱敏; Collector 异常会被吞掉.
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
        """绑定请求标识和采集器."""
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
        """构造事件并交给 Collector.

        Args:
            event_type: 事件类型.
            node_name: Graph 节点名.
            intent: 意图.
            route: 路由.
            tool_name: Tool 名.
            arguments_summary: 参数摘要, 会自动脱敏.
            risk_level: 风险等级.
            execution_status: 执行状态.
            duration_ms: 耗时.
            result_summary: 结果摘要, 会自动脱敏.
            error_code: 稳定错误码.
        """
        # ① 在边界统一脱敏, 调用方不需要重复处理.
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
        # ② 采集失败只丢弃观测, 绝不影响聊天主流程.
        try:
            self.collector.emit(event)
        except Exception:  # noqa: BLE001 - tracing must be best-effort
            # Observability is best-effort. A broken sink must not break chat.
            return
