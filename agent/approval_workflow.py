"""Minimal HITL approval subflow using LangGraph interrupt + checkpointer.

The Graph owns the pause/resume state for one approval. Redis/MySQL remain the
durable approval records; the in-memory checkpointer is intentionally a local
MVP choice and is documented as non-durable across process restarts.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class ApprovalWorkflowState(TypedDict, total=False):
    approval_id: str
    decision: dict[str, object]


async def wait_for_admin(state: ApprovalWorkflowState) -> dict[str, object]:
    """Pause the graph until an administrator approves or rejects."""
    decision = interrupt(
        {
            "approval_id": state["approval_id"],
            "question": "Approve this high-risk Agent action?",
        }
    )
    return {"decision": decision}


def build_approval_graph():
    builder = StateGraph(ApprovalWorkflowState)
    builder.add_node("wait_for_admin", wait_for_admin)
    builder.add_edge(START, "wait_for_admin")
    builder.add_edge("wait_for_admin", END)
    return builder.compile(checkpointer=InMemorySaver())


APPROVAL_WORKFLOW = build_approval_graph()


def _config(approval_id: str) -> dict[str, object]:
    return {"configurable": {"thread_id": f"agent-approval:{approval_id}"}}


async def start_approval(approval_id: str) -> None:
    """Create the paused Graph state; the plan itself is already durable."""
    await APPROVAL_WORKFLOW.ainvoke(
        {"approval_id": approval_id},
        config=_config(approval_id),
    )


async def resume_approval(approval_id: str, *, approved: bool) -> None:
    """Resume the same Graph thread with the administrator decision.

    The MVP uses an in-memory saver. If the process restarted after the
    durable approval was created, no in-memory thread exists; rebuild the
    interrupted thread before resuming so the durable MySQL decision still
    drives the same Graph contract.
    """
    config = _config(approval_id)
    try:
        await APPROVAL_WORKFLOW.ainvoke(
            Command(resume={"approved": approved}),
            config=config,
        )
    except Exception:  # noqa: BLE001 - missing in-memory thread is recoverable
        await start_approval(approval_id)
        await APPROVAL_WORKFLOW.ainvoke(
            Command(resume={"approved": approved}),
            config=config,
        )
