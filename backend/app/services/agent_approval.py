"""Agent 高风险操作审批 Service.

文件职责:
- 创建库存调整审批计划.
- 用 Redis 保存短期 pending, 用 MySQL 保存持久化审计.
- 提供管理员列表, 批准, 拒绝和消费者查询.
- 批准后恢复审批子图并调用 Business Service 执行.

核心流程:
create -> MySQL pending + Redis pending + start_approval
approve -> 锁行 -> 标记 approved -> resume_approval -> 重新校验库存
       -> InventoryService.adjust -> executed.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.approval_workflow import resume_approval, start_approval
from app.core.config import Settings, get_settings
from app.core.exceptions import (
    ConflictException,
    PermissionDeniedException,
    ResourceNotFoundException,
    ValidationException,
)
from app.db.redis import redis_client
from app.models.agent_approval import AgentApproval
from app.models.user import User
from app.services.inventory import InventoryService
from app.services.sku import SkuService

logger = logging.getLogger(__name__)

# 审批生命周期; 只有 pending 可以迁移到 approved 或 rejected.
ApprovalStatus = Literal[
    "pending",
    "approved",
    "rejected",
    "executed",
    "failed",
    "expired",
]


def _canonical(value: dict[str, Any]) -> str:
    """把参数序列化为稳定 JSON, 用于计算 action hash."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _hash(value: dict[str, Any]) -> str:
    """计算审批参数的 SHA-256."""
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    """返回不带时区信息的 UTC 时间, 与 MySQL DATETIME 保持一致."""
    return datetime.now(UTC).replace(tzinfo=None)


class AgentApprovalService:
    """创建, 查询, 审批和执行 Agent 高风险计划."""

    def __init__(
        self,
        session: AsyncSession,
        user: User,
        *,
        settings: Settings | None = None,
        redis: Redis | None = None,
    ) -> None:
        """保存当前用户和请求级依赖."""
        self.session = session
        self.user = user
        self.settings = settings or get_settings()
        self.redis = redis or redis_client

    @staticmethod
    def key(approval_id: str) -> str:
        """返回审批计划在 Redis 中的 key."""
        return f"agent:approval:{approval_id}"

    def _require_admin(self) -> None:
        """校验管理员权限, 普通用户不能查看或审批高风险计划."""
        if not self.user.is_admin:
            raise PermissionDeniedException(
                message="Administrator privileges are required",
            )

    async def create_inventory_adjustment(
        self,
        *,
        sku_code: str,
        quantity_delta: int,
        reason: str | None,
        conversation_id: str,
        thread_id: str,
    ) -> AgentApproval:
        """创建库存调整待审批计划, 不修改库存.

        Args:
            sku_code: 目标 SKU.
            quantity_delta: 调整数量, 可以为负.
            reason: 申请原因.
            conversation_id: 来源会话.
            thread_id: 审批子图线程标识.

        Returns:
            已持久化的 AgentApproval.

        Raises:
            PermissionDeniedException: 非管理员.
            ValidationException: 调整量为零.
            ConflictException: 调整后总量低于已预占量.
        """
        # ① 权限和数量预检查.
        self._require_admin()
        if quantity_delta == 0:
            raise ValidationException(
                message="Adjustment delta must not be zero",
                code="INVALID_QUANTITY",
            )

        # ② 读取当前库存并检查预占约束.
        sku, _product = await SkuService(self.session).get_sku_by_code(sku_code)
        inventory = await InventoryService(self.session).get_inventory(sku.id)
        new_total = inventory.total_quantity + quantity_delta
        if new_total < inventory.reserved_quantity:
            raise ConflictException(
                message="Adjustment would make total below reserved quantity",
                code="INVENTORY_RESERVED_CONFLICT",
            )

        arguments: dict[str, Any] = {
            "sku_code": sku_code,
            "quantity_delta": quantity_delta,
            "reason": reason,
        }
        before = {
            "total_quantity": inventory.total_quantity,
            "reserved_quantity": inventory.reserved_quantity,
            "available_quantity": inventory.total_quantity
            - inventory.reserved_quantity,
        }
        planned = {
            "total_quantity": new_total,
            "reserved_quantity": inventory.reserved_quantity,
            "available_quantity": new_total - inventory.reserved_quantity,
        }
        now = _utc_now()
        approval_id = secrets.token_urlsafe(24)
        record = AgentApproval(
            approval_id=approval_id,
            requester_id=self.user.id,
            conversation_id=conversation_id,
            thread_id=thread_id,
            operation="ADJUST_INVENTORY",
            resource_no=sku_code,
            arguments=arguments,
            before_data=before,
            planned_data=planned,
            action_hash=_hash(arguments),
            status="pending",
            expires_at=now
            + timedelta(seconds=self.settings.agent_approval_ttl_seconds),
        )
        # ③ 先持久化审计记录, 再写 Redis pending.
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)

        payload = {
            "approval_id": approval_id,
            "requester_id": self.user.id,
            "operation": "ADJUST_INVENTORY",
            "resource_no": sku_code,
            "arguments": arguments,
            "action_hash": record.action_hash,
            "status": "pending",
            "expires_at": int(record.expires_at.replace(tzinfo=UTC).timestamp()),
        }
        try:
            created = await self.redis.set(
                self.key(approval_id),
                _canonical(payload),
                ex=self.settings.agent_approval_ttl_seconds,
                nx=True,
            )
        except RedisError as exc:
            record.status = "failed"
            record.error_code = "AGENT_APPROVAL_UNAVAILABLE"
            await self.session.commit()
            raise ConflictException(
                message="Agent approval service is unavailable",
                code="AGENT_APPROVAL_UNAVAILABLE",
            ) from exc
        if not created:
            record.status = "failed"
            record.error_code = "AGENT_APPROVAL_DUPLICATE"
            await self.session.commit()
            raise ConflictException(
                message="Approval id collision",
                code="AGENT_APPROVAL_DUPLICATE",
            )
        # ④ 创建审批子图的暂停状态; 失败时标记审计记录失败.
        try:
            await start_approval(approval_id)
        except Exception as exc:
            record.status = "failed"
            record.error_code = "AGENT_APPROVAL_WORKFLOW_UNAVAILABLE"
            await self.session.commit()
            try:
                await self.redis.delete(self.key(approval_id))
            except RedisError:
                pass
            raise ConflictException(
                message="Agent approval workflow is unavailable",
                code="AGENT_APPROVAL_WORKFLOW_UNAVAILABLE",
            ) from exc
        return record

    async def list_approvals(
        self,
        *,
        status: ApprovalStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[AgentApproval], int]:
        """管理员分页查询审批列表, 可按状态过滤."""
        self._require_admin()
        statement = select(AgentApproval)
        count_statement = select(func.count()).select_from(AgentApproval)
        if status is not None:
            statement = statement.where(AgentApproval.status == status)
            count_statement = count_statement.where(AgentApproval.status == status)
        statement = (
            statement.order_by(AgentApproval.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list((await self.session.scalars(statement)).all())
        total = int((await self.session.scalar(count_statement)) or 0)
        return items, total

    async def get(self, approval_id: str) -> AgentApproval:
        """管理员按 ID 查询审批详情."""
        self._require_admin()
        record = await self.session.scalar(
            select(AgentApproval).where(
                AgentApproval.approval_id == approval_id,
            )
        )
        if record is None:
            raise ResourceNotFoundException(
                message="Agent approval was not found",
                code="AGENT_APPROVAL_NOT_FOUND",
            )
        return record

    async def list_for_requester(
        self,
        *,
        requester_id: int,
        status: ApprovalStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[AgentApproval], int]:
        """消费者分页查询自己发起的审批, 不能看到其他人的记录."""
        statement = select(AgentApproval).where(
            AgentApproval.requester_id == requester_id
        )
        count_statement = select(func.count()).select_from(AgentApproval).where(
            AgentApproval.requester_id == requester_id
        )
        if status is not None:
            statement = statement.where(AgentApproval.status == status)
            count_statement = count_statement.where(
                AgentApproval.status == status
            )
        statement = (
            statement.order_by(AgentApproval.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list((await self.session.scalars(statement)).all())
        total = int((await self.session.scalar(count_statement)) or 0)
        return items, total

    async def get_for_requester(
        self,
        *,
        requester_id: int,
        approval_id: str,
    ) -> AgentApproval:
        """消费者按 ID 查询自己的审批, 其他用户统一按不存在处理."""
        record = await self.session.scalar(
            select(AgentApproval).where(
                AgentApproval.approval_id == approval_id,
                AgentApproval.requester_id == requester_id,
            )
        )
        if record is None:
            raise ResourceNotFoundException(
                message="Agent approval was not found",
                code="AGENT_APPROVAL_NOT_FOUND",
            )
        return record

    async def _locked_pending(self, approval_id: str) -> AgentApproval:
        """锁定 pending 审批; 已处理或过期记录直接拒绝."""
        self._require_admin()
        record = await self.session.scalar(
            select(AgentApproval)
            .where(AgentApproval.approval_id == approval_id)
            .with_for_update()
        )
        if record is None:
            raise ResourceNotFoundException(
                message="Agent approval was not found",
                code="AGENT_APPROVAL_NOT_FOUND",
            )
        if record.status != "pending":
            raise ConflictException(
                message="Approval is no longer pending",
                code="AGENT_APPROVAL_NOT_PENDING",
            )
        if record.expires_at <= _utc_now():
            record.status = "expired"
            await self.session.commit()
            raise ConflictException(
                message="Approval has expired",
                code="AGENT_APPROVAL_EXPIRED",
            )
        return record

    async def _mark_failed(self, approval_id: str, code: str) -> None:
        """把已批准但执行失败的记录标记为 failed, 保留错误码."""
        record = await self.session.scalar(
            select(AgentApproval).where(
                AgentApproval.approval_id == approval_id,
            )
        )
        if record is not None and record.status in {"approved", "failed"}:
            record.status = "failed"
            record.error_code = code
            await self.session.commit()

    async def approve(
        self,
        approval_id: str,
        *,
        review_note: str | None = None,
    ) -> AgentApproval:
        """批准审批并执行原始计划.

        Args:
            approval_id: 审批编号.
            review_note: 管理员备注.

        Returns:
            执行成功的 AgentApproval.

        Raises:
            ConflictException: 审批已处理, 已过期, 库存已变化或执行失败.
        """
        # ① 行锁确认仍是 pending, 防止并发管理员重复批准.
        record = await self._locked_pending(approval_id)
        if record.operation != "ADJUST_INVENTORY":
            raise ConflictException(
                message="Unsupported approval operation",
                code="AGENT_APPROVAL_OPERATION_UNSUPPORTED",
            )

        # ② 先持久化批准决定, 再恢复审批子图.
        record.status = "approved"
        record.approver_id = self.user.id
        record.review_note = review_note
        record.reviewed_at = _utc_now()
        await self.session.commit()
        await self.session.refresh(record)
        try:
            await resume_approval(approval_id, approved=True)
        except Exception as exc:
            await self._mark_failed(approval_id, "AGENT_APPROVAL_RESUME_FAILED")
            raise ConflictException(
                message="Approval workflow could not be resumed",
                code="AGENT_APPROVAL_RESUME_FAILED",
            ) from exc

        try:
            # ③ 恢复后重新读取库存, 不能相信 Prepare 时的快照.
            sku_code = str(record.arguments["sku_code"])
            quantity_delta = int(record.arguments["quantity_delta"])
            sku, _product = await SkuService(self.session).get_sku_by_code(
                sku_code
            )
            inventory = await InventoryService(self.session).get_inventory(
                sku.id
            )
            if inventory.total_quantity != int(record.before_data["total_quantity"]):
                await self._mark_failed(approval_id, "AGENT_APPROVAL_STALE")
                raise ConflictException(
                    message="Inventory changed while approval was pending",
                    code="AGENT_APPROVAL_STALE",
                )
            # ④ 通过 InventoryService 执行, 使用 approval_id 作为幂等键.
            await InventoryService(self.session).adjust(
                sku_id=sku.id,
                quantity_delta=quantity_delta,
                idempotency_key=f"agent-approval:{approval_id}",
                operator_id=self.user.id,
                remark=f"Agent approval {approval_id}",
            )
        except ConflictException:
            raise
        except Exception as exc:
            await self._mark_failed(approval_id, "AGENT_APPROVAL_EXECUTION_FAILED")
            raise ConflictException(
                message="Approval execution failed",
                code="AGENT_APPROVAL_EXECUTION_FAILED",
            ) from exc

        # ⑤ 记录 executed 并清理 Redis pending.
        record = await self.session.scalar(
            select(AgentApproval).where(
                AgentApproval.approval_id == approval_id,
            )
        )
        if record is None:
            raise ResourceNotFoundException(
                message="Agent approval was not found",
                code="AGENT_APPROVAL_NOT_FOUND",
            )
        record.status = "executed"
        record.executed_at = _utc_now()
        await self.session.commit()
        await self.session.refresh(record)
        try:
            await self.redis.delete(self.key(approval_id))
        except RedisError:
            pass
        return record

    async def reject(
        self,
        approval_id: str,
        *,
        review_note: str | None = None,
    ) -> AgentApproval:
        """拒绝审批, 不执行任何业务写操作.

        Args:
            approval_id: 审批编号.
            review_note: 拒绝原因.

        Returns:
            状态为 rejected 的 AgentApproval.
        """
        # ① 行锁确保只有 pending 记录可以拒绝.
        record = await self._locked_pending(approval_id)
        record.status = "rejected"
        record.approver_id = self.user.id
        record.review_note = review_note
        record.reviewed_at = _utc_now()
        await self.session.commit()
        await self.session.refresh(record)
        # ② 恢复子图并传入拒绝决定; 即使恢复失败也不会执行业务.
        try:
            await resume_approval(approval_id, approved=False)
        except Exception as exc:  # noqa: BLE001 - durable rejection is final
            # The durable decision is rejected; no business write will run.
            logger.warning(
                "agent_approval_reject_resume_failed",
                extra={"approval_id": approval_id, "error": type(exc).__name__},
            )
        # ③ 清理 Redis pending.
        try:
            await self.redis.delete(self.key(approval_id))
        except RedisError:
            pass
        return record
