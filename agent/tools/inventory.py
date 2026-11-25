"""Inventory approval tool for the Agent workflow."""

from __future__ import annotations

from typing import Any

from app.services.agent_approval import AgentApprovalService
from pydantic import BaseModel

from agent.tools.context import ToolContext
from agent.tools.errors import ToolResult
from agent.tools.schemas import PrepareAdjustInventoryInput


async def prepare_adjust_inventory(
    context: ToolContext,
    raw_args: BaseModel,
) -> ToolResult:
    """Create a pending approval; never change inventory in this tool."""
    args = PrepareAdjustInventoryInput.model_validate(raw_args.model_dump())
    service = AgentApprovalService(
        context.session,
        context.user,
        settings=context.settings,
    )
    approval = await service.create_inventory_adjustment(
        sku_code=args.sku_code,
        quantity_delta=args.quantity_delta,
        reason=args.reason,
        conversation_id=str(context.conversation_id),
        thread_id=str(context.conversation_id),
    )
    pending: dict[str, Any] = {
        "confirmation_id": approval.approval_id,
        "nonce": "",
        "conversation_id": str(context.conversation_id),
        "action_type": "ADJUST_INVENTORY",
        "title": "库存调整待管理员审批",
        "resource_no": approval.resource_no,
        "effect": (
            f"库存 {approval.before_data['total_quantity']} → "
            f"{approval.planned_data['total_quantity']}"
        ),
        "summary": args.reason,
        "expires_at": approval.expires_at.isoformat(),
        "approval_required": True,
        "approval_id": approval.approval_id,
        "approval_status": approval.status,
    }
    return ToolResult(
        ok=True,
        tool="prepare_adjust_inventory",
        data={
            "approval_id": approval.approval_id,
            "status": approval.status,
            "before": approval.before_data,
            "planned": approval.planned_data,
        },
        pending_action=pending,
    )
