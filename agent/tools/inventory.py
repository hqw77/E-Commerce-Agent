"""库存调整的 Agent PREPARE Tool.

文件职责:
- 把模型生成的 SKU/数量/原因转换成审批计划.
- 创建 Redis pending 和 MySQL 审计记录.
- 返回前端展示所需的 pending_action.

核心边界:
本 Tool 绝不直接修改库存; 真正执行发生在管理员批准后的 ApprovalService.
"""

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
    """创建库存调整审批计划.

    Args:
        context: 当前用户和请求级依赖.
        raw_args: 模型返回的原始参数.

    Returns:
        ToolResult, pending_action 中包含 approval_id 和审批展示字段.

    Raises:
        PermissionDeniedException: 非管理员尝试发起库存调整.
        ValidationException: 调整数量为零.
        ConflictException: 调整后总量低于已预占量.
    """
    # ① 用 Tool Schema 再校验一次模型参数, 不信任模型输出.
    args = PrepareAdjustInventoryInput.model_validate(raw_args.model_dump())
    service = AgentApprovalService(
        context.session,
        context.user,
        settings=context.settings,
    )
    # ② AgentApprovalService 负责权限, 预检查和审批记录持久化.
    approval = await service.create_inventory_adjustment(
        sku_code=args.sku_code,
        quantity_delta=args.quantity_delta,
        reason=args.reason,
        conversation_id=str(context.conversation_id),
        thread_id=str(context.conversation_id),
    )
    # ③ 统一 pending_action 结构, 兼容用户确认和管理员审批两种路径.
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
