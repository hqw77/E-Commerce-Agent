"""Agent 执行 Trace 事件结构.

文件职责:
- 定义一次请求中节点, 路由, RAG, Tool 事件的统一字段.
- 让日志和调试台使用同一份结构.

核心边界:
事件只保存脱敏摘要, 不保存 Prompt 和完整业务数据.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

# 事件执行状态.
TraceStatus = Literal["STARTED", "SUCCESS", "ERROR", "EMPTY", "SKIPPED"]
# 高风险 Tool 的风险等级.
RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]


@dataclass(frozen=True, slots=True)
class TraceEvent:
    """一次 Trace 中的不可变事件.

    Args:
        trace_id: 本次请求的 Trace ID.
        request_id: HTTP 请求 ID.
        conversation_id: 会话 ID.
        user_id: 用户 ID.
        event_type: node_start/node_end 等事件类型.
        node_name: Graph 节点名.
        intent: 意图标签.
        route: 路由标签.
        tool_name: Tool 名.
        arguments_summary: 脱敏后的参数摘要.
        risk_level: 风险等级.
        execution_status: 执行状态.
        duration_ms: 节点耗时.
        result_summary: 脱敏后的结果摘要.
        error_code: 稳定错误码.
        timestamp: ISO 时间.
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
        """转成 JSON 友好的字典."""
        return asdict(self)
