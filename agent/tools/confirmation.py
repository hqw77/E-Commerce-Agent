"""Redis-backed one-time Prepare/Confirm records for Agent actions."""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from app.core.config import Settings, get_settings
from app.db.redis import redis_client
from app.models.user import User
from app.schemas.after_sale import AfterSaleApplyRequest
from app.services.after_sale import AfterSaleService
from app.services.order import OrderService
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from agent.tools.errors import (
    AgentConfirmationConsumedError,
    AgentConfirmationExpiredError,
    AgentConfirmationMismatchError,
    AgentConfirmationNotFoundError,
    AgentConfirmationUnavailableError,
)

ActionType = Literal["CANCEL_ORDER", "APPLY_AFTER_SALE"]

_CONSUME_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then
    return {0}
end
local data = cjson.decode(raw)
if data['status'] ~= 'PREPARED' then
    return {2}
end
if tostring(data['user_id']) ~= ARGV[1] then
    return {3}
end
if data['conversation_id'] ~= ARGV[2] then
    return {3}
end
if data['nonce'] ~= ARGV[3] then
    return {3}
end
if tonumber(data['expires_at']) < tonumber(ARGV[4]) then
    return {4}
end
redis.call('DEL', KEYS[1])
return {1, raw}
"""


@dataclass(frozen=True, slots=True)
class ConfirmationRecord:
    confirmation_id: str
    user_id: int
    conversation_id: str
    operation: ActionType
    tool_name: str
    resource_no: str
    arguments: dict[str, Any]
    params_hash: str
    nonce: str
    expires_at: int


@dataclass(frozen=True, slots=True)
class ConfirmationOffer:
    confirmation_id: str
    nonce: str
    conversation_id: UUID
    operation: ActionType
    resource_no: str
    expires_at: int
    summary: str


@dataclass(frozen=True, slots=True)
class ConfirmationResult:
    operation: ActionType
    resource_no: str
    status: str
    message: str
    after_sales_no: str | None = None


def canonical_arguments(arguments: dict[str, Any]) -> str:
    return json.dumps(
        arguments,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def arguments_hash(arguments: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_arguments(arguments).encode("utf-8")).hexdigest()


class ConfirmationStore:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        redis: Redis | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.redis = redis or redis_client

    @staticmethod
    def key(confirmation_id: str) -> str:
        return f"agent:action:confirmation:{confirmation_id}"

    async def create(
        self,
        *,
        user_id: int,
        conversation_id: UUID,
        operation: ActionType,
        tool_name: str,
        resource_no: str,
        arguments: dict[str, Any],
        summary: str,
    ) -> ConfirmationOffer:
        now = int(time.time())
        expiry = now + self.settings.agent_action_confirmation_ttl_seconds
        for _ in range(3):
            confirmation_id = secrets.token_urlsafe(32)
            nonce = secrets.token_urlsafe(32)
            record = {
                "confirmation_id": confirmation_id,
                "user_id": user_id,
                "conversation_id": str(conversation_id),
                "operation": operation,
                "tool_name": tool_name,
                "resource_no": resource_no,
                "arguments": arguments,
                "params_hash": arguments_hash(arguments),
                "nonce": nonce,
                "status": "PREPARED",
                "created_at": now,
                "expires_at": expiry,
                "summary": summary,
            }
            try:
                created = await self.redis.set(
                    self.key(confirmation_id),
                    json.dumps(record, ensure_ascii=False),
                    ex=self.settings.agent_action_confirmation_ttl_seconds,
                    nx=True,
                )
            except RedisError as exc:
                raise AgentConfirmationUnavailableError() from exc
            if created:
                return ConfirmationOffer(
                    confirmation_id=confirmation_id,
                    nonce=nonce,
                    conversation_id=conversation_id,
                    operation=operation,
                    resource_no=resource_no,
                    expires_at=expiry,
                    summary=summary,
                )
        raise AgentConfirmationUnavailableError()

    async def consume(
        self,
        *,
        confirmation_id: str,
        user_id: int,
        conversation_id: UUID,
        nonce: str,
    ) -> ConfirmationRecord:
        try:
            raw = await self.redis.eval(
                _CONSUME_SCRIPT,
                1,
                self.key(confirmation_id),
                str(user_id),
                str(conversation_id),
                nonce,
                str(int(time.time())),
            )
        except RedisError as exc:
            raise AgentConfirmationUnavailableError() from exc

        code = int(raw[0]) if raw else 0
        if code == 0:
            raise AgentConfirmationNotFoundError()
        if code == 2:
            raise AgentConfirmationConsumedError()
        if code == 3:
            raise AgentConfirmationMismatchError()
        if code == 4:
            raise AgentConfirmationExpiredError()

        try:
            data = json.loads(raw[1])
            arguments = data["arguments"]
            if arguments_hash(arguments) != data["params_hash"]:
                raise AgentConfirmationMismatchError()
            return ConfirmationRecord(
                confirmation_id=data["confirmation_id"],
                user_id=int(data["user_id"]),
                conversation_id=data["conversation_id"],
                operation=data["operation"],
                tool_name=data["tool_name"],
                resource_no=data["resource_no"],
                arguments=arguments,
                params_hash=data["params_hash"],
                nonce=data["nonce"],
                expires_at=int(data["expires_at"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AgentConfirmationUnavailableError() from exc


class ConfirmationService:
    def __init__(
        self,
        session: AsyncSession,
        user: User,
        *,
        store: ConfirmationStore | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.user = user
        self.settings = settings or get_settings()
        self.store = store or ConfirmationStore(self.settings)

    async def confirm(
        self,
        *,
        confirmation_id: str,
        conversation_id: UUID,
        nonce: str,
    ) -> ConfirmationResult:
        record = await self.store.consume(
            confirmation_id=confirmation_id,
            user_id=self.user.id,
            conversation_id=conversation_id,
            nonce=nonce,
        )
        expected_resource = record.arguments.get("order_no")
        if (
            record.operation not in {"CANCEL_ORDER", "APPLY_AFTER_SALE"}
            or record.resource_no != expected_resource
        ):
            raise AgentConfirmationMismatchError()
        if record.operation == "CANCEL_ORDER":
            order = await OrderService(self.session).cancel_order(
                user_id=self.user.id,
                order_no=record.resource_no,
                reason=record.arguments.get("reason"),
            )
            return ConfirmationResult(
                operation="CANCEL_ORDER",
                resource_no=order.order_no,
                status=order.status,
                message="订单已取消。",
            )
        if record.operation == "APPLY_AFTER_SALE":
            request = AfterSaleApplyRequest(
                sku_code=record.arguments["sku_code"],
                type=record.arguments["type"],
                reason=record.arguments["reason"],
                description=record.arguments.get("description"),
                evidence_urls=record.arguments.get("evidence_urls"),
                idempotency_key=f"agent-confirm:{record.confirmation_id}",
            )
            after_sale = await AfterSaleService(self.session).apply(
                user_id=self.user.id,
                order_no=record.resource_no,
                request=request,
            )
            return ConfirmationResult(
                operation="APPLY_AFTER_SALE",
                resource_no=record.resource_no,
                status=after_sale.status,
                message="售后申请已提交，等待审核。",
                after_sales_no=after_sale.after_sales_no,
            )
        raise AgentConfirmationMismatchError()
