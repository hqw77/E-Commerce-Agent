"""Agent 输入/输出安全流水线.

文件职责:
- 组合输入清洗, Prompt 注入诊断和输出校验.
- 把护栏结果整理成可供 Runtime 使用的 SafetyInput.

核心边界:
不实现认证, 资源归属, 业务状态校验或数据库访问.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.schemas.knowledge import RetrievalItem

from agent.guardrails import (
    looks_like_prompt_injection,
    validate_output,
    validate_user_message,
)
from agent.state import SourceRef


@dataclass(frozen=True, slots=True)
class SafetyInput:
    """清洗后的输入和非权威安全信号.

    Args:
        message: 清洗后的用户消息.
        injection_suspected: 是否命中注入启发式.
        check_degraded: 诊断器异常时为 True.
    """

    message: str
    injection_suspected: bool
    check_degraded: bool


class SafetyPipeline:
    """现有确定性护栏的轻量组合层."""

    def __init__(self, settings: Settings) -> None:
        """初始化实例依赖."""
        self.settings = settings

    def check_input(self, message: str) -> SafetyInput:
        """清洗输入并产生诊断信号.

        注入检测异常时 fail-open, 因为该信号只用于观测.
        """
        normalized = validate_user_message(message, self.settings)
        suspected = False
        degraded = False
        try:
            suspected = looks_like_prompt_injection(normalized)
        except Exception:  # noqa: BLE001 - fail open on the diagnostic signal
            # A broken heuristic must not make the Agent unavailable. The
            # signal is diagnostic, not an authorization boundary.
            degraded = True
        return SafetyInput(
            message=normalized,
            injection_suspected=suspected,
            check_degraded=degraded,
        )

    def validate_output(
        self,
        answer: str,
        *,
        sources: list[SourceRef],
        retrieved_items: list[RetrievalItem],
    ) -> str:
        """复用 guardrails 的输出校验."""
        return validate_output(
            answer,
            sources=sources,
            retrieved_items=retrieved_items,
            settings=self.settings,
        )
