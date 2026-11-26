"""用户 Prepare / Confirm 的一次性确认存储.

文件职责:
- Prepare 阶段把待执行动作写入 Redis.
- Confirm 阶段用 Lua 原子消费记录, 再调用 Business Service 执行.
- 记录只保存短期 pending, MySQL 业务表才是最终状态.

核心边界:
这是用户自助确认路径, 与管理员 HITL 审批是两条独立路径.
"""

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

# 当前只允许取消订单和申请售后两类用户确认动作.
ActionType = Literal["CANCEL_ORDER", "APPLY_AFTER_SALE"]

# Lua 原子校验并删除确认记录, 防止并发请求重复执行业务.
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
    """从 Redis 消费出的完整待执行记录.

    Args:
        confirmation_id: 一次性确认 ID.
        user_id: 发起用户.
        conversation_id: 所属会话.
        operation: 取消订单或申请售后.
        tool_name: 生成记录的 PREPARE Tool.
        resource_no: 订单号.
        arguments: 待执行参数.
        params_hash: 参数 SHA-256, 防止内容被替换.
        nonce: 确认随机数.
        expires_at: Unix 过期时间.
    """

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
    """Prepare 阶段返回给前端的确认凭证.

    Args:
        confirmation_id: 一次性确认 ID.
        nonce: 确认随机数.
        conversation_id: 所属会话.
        operation: 待执行动作.
        resource_no: 业务编号.
        expires_at: Unix 过期时间.
        summary: 面向用户的摘要.
    """

    confirmation_id: str
    nonce: str
    conversation_id: UUID
    operation: ActionType
    resource_no: str
    expires_at: int
    summary: str


@dataclass(frozen=True, slots=True)
class ConfirmationResult:
    """Confirm 执行完成后的业务结果.

    Args:
        operation: 已执行动作.
        resource_no: 业务编号.
        status: Service 返回的状态.
        message: 面向用户的结果说明.
        after_sales_no: 售后单号, 取消订单时为 None.
    """

    operation: ActionType
    resource_no: str
    status: str
    message: str
    after_sales_no: str | None = None


def canonical_arguments(arguments: dict[str, Any]) -> str:
    """把参数序列化为稳定字符串, 保证相同内容得到相同 hash."""
    return json.dumps(
        arguments,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def arguments_hash(arguments: dict[str, Any]) -> str:
    """计算参数 SHA-256, 用于绑定审批/确认内容."""
    return hashlib.sha256(canonical_arguments(arguments).encode("utf-8")).hexdigest()


# 这是用户自助确认路径; 管理员 HITL 审批使用 AgentApprovalService, 两者不能混用.
class ConfirmationStore:
    """Redis 中的一次性确认记录存储."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        redis: Redis | None = None,
    ) -> None:
        """初始化实例依赖."""
        self.settings = settings or get_settings()
        self.redis = redis or redis_client

    @staticmethod
    def key(confirmation_id: str) -> str:
        """返回确认记录在 Redis 中的固定 key."""
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
        """创建一次性 pending 记录.

        Returns:
            给前端的确认凭证, 包含 nonce 和过期时间.
        """
        now = int(time.time())
        # ① 设置 TTL 并生成不可预测的 confirmation_id 和 nonce.
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
        """原子消费一条确认记录.

        Args:
            confirmation_id: Prepare 返回的 ID.
            user_id: 当前用户, 必须与记录一致.
            conversation_id: 当前会话, 必须与记录一致.
            nonce: Prepare 返回的随机数.

        Returns:
            校验通过的 ConfirmationRecord.

        Raises:
            AgentConfirmationNotFoundError: 记录不存在.
            AgentConfirmationConsumedError: 记录已被消费.
            AgentConfirmationMismatchError: 用户, 会话或 nonce 不匹配.
            AgentConfirmationExpiredError: 记录已过期.
        """
        try:
            # ① Lua 在一次 Redis 操作中完成状态, 用户, 会话, nonce 和 TTL 校验.
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

        # ② 把 Lua 返回码转换为明确的业务异常.
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
            # ③ 反序列化后再次校验参数 hash, 防止 Redis 内容被替换.
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
    """把用户确认转换成真实 Business Service 调用."""

    def __init__(
        self,
        session: AsyncSession,
        user: User,
        *,
        store: ConfirmationStore | None = None,
        settings: Settings | None = None,
    ) -> None:
        """初始化实例依赖."""
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
        """消费确认并执行对应业务动作.

        Args:
            confirmation_id: Prepare 返回的 ID.
            conversation_id: 当前会话 ID.
            nonce: Prepare 返回的随机数.

        Returns:
            业务执行结果.

        Raises:
            AgentConfirmationMismatchError: 参数资源与记录不一致.
        """
        record = await self.store.consume(
            confirmation_id=confirmation_id,
            user_id=self.user.id,
            conversation_id=conversation_id,
            nonce=nonce,
        )
        # 消费成功后才调用 Service; Prepare 阶段的快照不能替代当前业务校验.
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
