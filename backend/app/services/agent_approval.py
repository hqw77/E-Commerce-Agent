"""Agent high-risk approval service.

Redis holds the short-lived pending plan; MySQL ``agent_approvals`` is the
durable audit and state source. The execution path still goes through the
existing business Service, never directly through SQL in the Agent layer.
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

ApprovalStatus = Literal[
    "pending",
    "approved",
    "rejected",
    "executed",
    "failed",
    "expired",
]


def _canonical(value: dict[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class AgentApprovalService:
    """Create, list, review and execute Agent high-risk approvals."""

    def __init__(
        self,
        session: AsyncSession,
        user: User,
        *,
        settings: Settings | None = None,
        redis: Redis | None = None,
    ) -> None:
        self.session = session
        self.user = user
        self.settings = settings or get_settings()
        self.redis = redis or redis_client

    @staticmethod
    def key(approval_id: str) -> str:
        return f"agent:approval:{approval_id}"

    def _require_admin(self) -> None:
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
        """Prepare an inventory adjustment; never writes inventory here."""
        self._require_admin()
        if quantity_delta == 0:
            raise ValidationException(
                message="Adjustment delta must not be zero",
                code="INVALID_QUANTITY",
            )

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

    async def _locked_pending(self, approval_id: str) -> AgentApproval:
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
        """Approve then execute the saved plan through InventoryService."""
        record = await self._locked_pending(approval_id)
        if record.operation != "ADJUST_INVENTORY":
            raise ConflictException(
                message="Unsupported approval operation",
                code="AGENT_APPROVAL_OPERATION_UNSUPPORTED",
            )

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
        record = await self._locked_pending(approval_id)
        record.status = "rejected"
        record.approver_id = self.user.id
        record.review_note = review_note
        record.reviewed_at = _utc_now()
        await self.session.commit()
        await self.session.refresh(record)
        try:
            await resume_approval(approval_id, approved=False)
        except Exception as exc:  # noqa: BLE001 - durable rejection is final
            # The durable decision is rejected; no business write will run.
            logger.warning(
                "agent_approval_reject_resume_failed",
                extra={"approval_id": approval_id, "error": type(exc).__name__},
            )
        try:
            await self.redis.delete(self.key(approval_id))
        except RedisError:
            pass
        return record
