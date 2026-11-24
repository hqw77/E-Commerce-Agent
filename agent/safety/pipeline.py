"""Safety pipeline for Agent input and output boundaries."""

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
    """Normalized input plus non-authoritative safety signals."""

    message: str
    injection_suspected: bool
    check_degraded: bool


class SafetyPipeline:
    """Thin composition of existing deterministic guardrails.

    This class deliberately does not implement authentication, ownership,
    business state validation, or database access. Those remain in the API,
    ToolContext and Backend Service layers.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def check_input(self, message: str) -> SafetyInput:
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
        return validate_output(
            answer,
            sources=sources,
            retrieved_items=retrieved_items,
            settings=self.settings,
        )
