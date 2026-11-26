"""售后 Repository.

文件职责:
- 封装售后记录查询和创建.
- 提供用户隔离, 订单关联和幂等键查询.

核心边界:
Repository 只做 SQL; 售后状态迁移和资格判断属于 AfterSaleService.
"""

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.after_sale import AfterSale

# 这些状态表示售后仍占用订单项, 同一订单项不能重复申请.
ACTIVE_AFTER_SALE_STATUSES = (
    "PENDING_REVIEW",
    "APPROVED",
    "WAITING_RETURN",
    "RETURN_SHIPPED",
    "RECEIVED",
    "REFUNDING",
    "REFUND_FAILED",
)


class AfterSaleRepository:
    """售后表的数据库访问对象."""

    def __init__(self, session: AsyncSession) -> None:
        """初始化实例依赖."""
        self.session = session

    async def create(self, after_sale: AfterSale) -> AfterSale:
        """加入并刷新新售后记录."""
        self.session.add(after_sale)
        await self.session.flush()
        await self.session.refresh(after_sale)
        return after_sale

    async def save(self, after_sale: AfterSale) -> AfterSale:
        """刷新已修改售后, 不主动 commit."""
        await self.session.flush()
        await self.session.refresh(after_sale)
        return after_sale

    async def get_by_no(
        self,
        after_sales_no: str,
        *,
        for_update: bool = False,
    ) -> AfterSale | None:
        """按售后编号读取, 可选行锁."""
        statement = select(AfterSale).where(AfterSale.after_sales_no == after_sales_no)
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_id(self, after_sales_id: int) -> AfterSale | None:
        """按主键读取售后."""
        statement = select(AfterSale).where(AfterSale.id == after_sales_id)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_id_for_update(
        self,
        after_sales_id: int,
    ) -> AfterSale | None:
        """按主键读取并加行锁."""
        statement = (
            select(AfterSale).where(AfterSale.id == after_sales_id).with_for_update()
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_user_and_key(
        self,
        user_id: int,
        idempotency_key: str,
        *,
        for_update: bool = False,
    ) -> AfterSale | None:
        """按用户和幂等键读取售后."""
        statement = select(AfterSale).where(
            AfterSale.user_id == user_id,
            AfterSale.idempotency_key == idempotency_key,
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_active_for_item(
        self,
        order_item_id: int,
        *,
        for_update: bool = False,
    ) -> AfterSale | None:
        """读取订单项当前仍活跃的售后, 防止重复申请."""
        statement = select(AfterSale).where(
            AfterSale.order_item_id == order_item_id,
            AfterSale.status.in_(ACTIVE_AFTER_SALE_STATUSES),
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: int,
        *,
        page: int,
        page_size: int,
    ) -> list[AfterSale]:
        """分页查询当前用户售后."""
        statement = (
            select(AfterSale)
            .where(AfterSale.user_id == user_id)
            .order_by(AfterSale.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def count_for_user(self, user_id: int) -> int:
        """统计当前用户售后数量."""
        statement = select(func.count(AfterSale.id)).where(AfterSale.user_id == user_id)
        result = await self.session.execute(statement)
        return int(result.scalar_one())

    async def list_for_order(self, order_id: int) -> list[AfterSale]:
        """按订单读取全部售后, 供订单详情展示."""
        statement = (
            select(AfterSale)
            .where(AfterSale.order_id == order_id)
            .order_by(AfterSale.id.asc())
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def list_admin(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
    ) -> list[AfterSale]:
        """管理员分页查询售后."""
        statement = select(AfterSale)
        if status:
            statement = statement.where(AfterSale.status == status)
        statement = (
            statement.order_by(AfterSale.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def count_admin(self, *, status: str | None = None) -> int:
        """统计全部或指定状态售后数量."""
        statement = select(func.count(AfterSale.id))
        if status:
            statement = statement.where(AfterSale.status == status)
        result = await self.session.execute(statement)
        return int(result.scalar_one())

    @staticmethod
    def same_fingerprint(
        after_sale: AfterSale,
        *,
        order_id: int,
        order_item_id: int,
        type: str,
        quantity: int,
        requested_amount: Decimal,
        reason: str,
        description: str | None,
        evidence_urls: list[str] | None,
    ) -> bool:
        """比较已存在售后与本次参数是否完全一致."""
        return (
            after_sale.order_id == order_id
            and after_sale.order_item_id == order_item_id
            and after_sale.type == type
            and after_sale.quantity == quantity
            and after_sale.requested_amount == requested_amount
            and after_sale.reason == reason
            and after_sale.description == description
            and after_sale.evidence_urls == evidence_urls
        )


def after_sale_fingerprint_payload(
    *,
    order_no: str,
    sku_code: str,
    type: str,
    quantity: int,
    reason: str,
    description: str | None,
    evidence_urls: list[str] | None,
) -> dict[str, Any]:
    """构造售后幂等指纹的稳定 payload."""
    return {
        "order_no": order_no,
        "sku_code": sku_code,
        "type": type,
        "quantity": quantity,
        "reason": reason,
        "description": description,
        "evidence_urls": evidence_urls,
    }
