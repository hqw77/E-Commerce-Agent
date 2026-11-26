"""库存调整 HITL 审批子图.

文件职责:
- 用 LangGraph interrupt 暂停审批.
- 用 Command(resume=...) 恢复同一 thread.
- 只保存中断所需状态, 审批正文和业务状态以 Redis/MySQL 为准.

核心限制:
当前使用 InMemorySaver. 进程重启会丢失 Graph 线程; 审批记录仍在 MySQL,
恢复时会重建中断再继续.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class ApprovalWorkflowState(TypedDict, total=False):
    """审批子图的最小状态.

    Args:
        approval_id: 审批记录 ID, 同时用于派生 thread_id.
        decision: 管理员的批准或拒绝决定.
    """

    approval_id: str
    decision: dict[str, object]


async def wait_for_admin(state: ApprovalWorkflowState) -> dict[str, object]:
    """暂停子图, 等待管理员决定.

    Args:
        state: 包含 approval_id 的审批状态.

    Returns:
        管理员通过 Command(resume=...) 传回的决定.
    """
    # interrupt 在此暂停 Graph; 管理员批准/拒绝后由 Command(resume=...) 继续.
    decision = interrupt(
        {
            "approval_id": state["approval_id"],
            "question": "Approve this high-risk Agent action?",
        }
    )
    return {"decision": decision}


def build_approval_graph():
    """构建只包含等待节点的审批子图.

    Returns:
        编译后的 StateGraph, 使用 InMemorySaver 保存暂停状态.
    """
    builder = StateGraph(ApprovalWorkflowState)
    builder.add_node("wait_for_admin", wait_for_admin)
    builder.add_edge(START, "wait_for_admin")
    builder.add_edge("wait_for_admin", END)
    # 当前使用 InMemorySaver; 进程重启会丢失 Graph 线程, 但 MySQL 审批记录仍在.
    return builder.compile(checkpointer=InMemorySaver())


APPROVAL_WORKFLOW = build_approval_graph()


def _config(approval_id: str) -> dict[str, object]:
    """用 approval_id 派生稳定的 Graph thread_id."""
    return {"configurable": {"thread_id": f"agent-approval:{approval_id}"}}


async def start_approval(approval_id: str) -> None:
    """启动审批子图并停在 interrupt.

    Args:
        approval_id: 已持久化的审批记录 ID.
    """
    await APPROVAL_WORKFLOW.ainvoke(
        {"approval_id": approval_id},
        config=_config(approval_id),
    )


async def resume_approval(approval_id: str, *, approved: bool) -> None:
    """恢复审批子图并传入管理员决定.

    Args:
        approval_id: 审批记录 ID.
        approved: True 表示批准, False 表示拒绝.
    """
    config = _config(approval_id)
    try:
        await APPROVAL_WORKFLOW.ainvoke(
            Command(resume={"approved": approved}),
            config=config,
        )
    except Exception:  # noqa: BLE001 - missing in-memory thread is recoverable
        # 进程重启导致内存线程丢失时, 先重建中断再恢复; 仍不执行任何业务写操作.
        await start_approval(approval_id)
        await APPROVAL_WORKFLOW.ainvoke(
            Command(resume={"approved": approved}),
            config=config,
        )
