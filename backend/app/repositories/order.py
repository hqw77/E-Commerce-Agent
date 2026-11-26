"""订单 Repository.

文件职责:
- 封装订单表查询和预加载.
- 提供按订单号, 用户, 幂等键和分页读取.

核心边界:
Repository 只做 SQL, 不判断订单状态, 不提交事务.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.order import Order


class OrderRepository:
    """订单表的数据库访问对象."""

    def __init__(self, session: AsyncSession) -> None:
        """初始化实例依赖."""
        self.session = session

    async def create(self, order: Order) -> Order:
        """把新订单加入当前事务并刷新数据库生成字段."""
        self.session.add(order)
        await self.session.flush()
        await self.session.refresh(order)
        return order

    async def save(self, order: Order) -> Order:
        """刷新已修改订单, 不主动 commit."""
        await self.session.flush()
        await self.session.refresh(order)
        return order

    async def get_by_no(
        self,
        order_no: str,
        *,
        for_update: bool = False,
        with_items: bool = False,
    ) -> Order | None:
        """按订单号读取; 可加行锁或预加载订单项."""
        statement = select(Order).where(Order.order_no == order_no)
        if with_items:
            statement = statement.options(selectinload(Order.items))
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_id(
        self,
        order_id: int,
        *,
        for_update: bool = False,
    ) -> Order | None:
        """按主键读取订单, 可选行锁."""
        statement = select(Order).where(Order.id == order_id)
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_user_and_key(
        self,
        user_id: int,
        idempotency_key: str,
        *,
        for_update: bool = False,
    ) -> Order | None:
        """按用户和幂等键读取订单, 用于识别重复提交."""
        statement = select(Order).where(
            Order.user_id == user_id,
            Order.idempotency_key == idempotency_key,
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
        status: str | None = None,
    ) -> list[Order]:
        """分页查询当前用户订单, 预加载订单项."""
        statement = select(Order).where(Order.user_id == user_id)
        if status:
            statement = statement.where(Order.status == status)
        statement = (
            statement.options(selectinload(Order.items))
            .order_by(Order.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def count_for_user(
        self,
        user_id: int,
        *,
        status: str | None = None,
    ) -> int:
        """统计当前用户订单数量."""
        statement = select(func.count(Order.id)).where(Order.user_id == user_id)
        if status:
            statement = statement.where(Order.status == status)
        result = await self.session.execute(statement)
        return int(result.scalar_one())

    async def list_admin(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
    ) -> list[Order]:
        """管理员分页查询全部订单."""
        statement = select(Order)
        if status:
            statement = statement.where(Order.status == status)
        statement = (
            statement.options(selectinload(Order.items))
            .order_by(Order.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def count_admin(self, *, status: str | None = None) -> int:
        """统计全部订单或指定状态数量."""
        statement = select(func.count(Order.id))
        if status:
            statement = statement.where(Order.status == status)
        result = await self.session.execute(statement)
        return int(result.scalar_one())
