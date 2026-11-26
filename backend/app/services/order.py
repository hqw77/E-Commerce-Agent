"""订单生命周期 Service.

文件职责:
- 创建订单并预占库存.
- 取消未发货订单并释放预占.
- 管理员发货, 送达和完成订单.
- 处理用户隔离和幂等键.

核心边界:
当前没有支付和资金退款. 新订单从 CREATED/UNSHIPPED 开始.
所有状态变更都通过 transaction_context 和库存 Service 完成.
"""

from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ConflictException, ResourceNotFoundException
from app.models.order import Order
from app.models.product import Product
from app.models.sku import Sku
from app.repositories.inventory import InventoryRepository
from app.repositories.order import OrderRepository
from app.repositories.order_item import OrderItemRepository
from app.repositories.product import ProductRepository
from app.repositories.sku import SkuRepository
from app.schemas.order import OrderCreateRequest, ShipOrderRequest
from app.services.inventory import InventoryService
from app.services.transaction import transaction_context
from app.utils.order import money, new_order_no, request_fingerprint, utc_after, utc_now

# 历史 PAID 订单仍需支持发货; 新订单不会再进入 PAID 状态.
LEGACY_SHIPPABLE_STATUSES = {"CREATED", "PAID"}


class OrderService:
    """订单创建, 取消, 发货, 送达和完成规则."""

    def __init__(self, session: AsyncSession) -> None:
        """绑定当前请求 session 和所需 Repository/Service."""
        self.session = session
        self.orders = OrderRepository(session)
        self.items = OrderItemRepository(session)
        self.products = ProductRepository(session)
        self.skus = SkuRepository(session)
        self.inventories = InventoryRepository(session)
        self.inventory = InventoryService(session)

    @staticmethod
    def _fingerprint(request: OrderCreateRequest) -> str:
        """计算下单参数指纹, 用于幂等键冲突检测."""
        return request_fingerprint(
            items=[
                {"sku_code": item.sku_code, "quantity": item.quantity}
                for item in request.items
            ],
            receiver_name=request.receiver_name,
            receiver_phone=request.receiver_phone,
            receiver_address=request.receiver_address,
            customer_remark=request.customer_remark,
        )

    @staticmethod
    def _is_idempotency_conflict(exc: IntegrityError) -> bool:
        """判断 IntegrityError 是否来自订单幂等唯一约束."""
        return "uq_orders_user_idempotency" in str(exc.orig)

    async def _detail(self, order_no: str) -> Order:
        """读取含订单项的订单详情, 不存在时抛 404."""
        order = await self.orders.get_by_no(order_no, with_items=True)
        if order is None:
            raise ResourceNotFoundException(
                message="Order not found",
                code="ORDER_NOT_FOUND",
            )
        return order

    async def _existing_or_conflict(
        self,
        *,
        user_id: int,
        idempotency_key: str,
        fingerprint: str,
    ) -> Order | None:
        """命中幂等键时返回旧订单; 参数不同则拒绝复用."""
        existing = await self.orders.get_by_user_and_key(
            user_id,
            idempotency_key,
        )
        if existing is None:
            return None
        if existing.request_fingerprint != fingerprint:
            raise ConflictException(
                message="Idempotency key was used with different parameters",
                code="IDEMPOTENCY_KEY_CONFLICT",
            )
        return await self._detail(existing.order_no)

    async def _load_purchase_lines(
        self,
        request: OrderCreateRequest,
    ) -> list[tuple[Product, Sku, int, Decimal]]:
        """校验 SKU, 商品和可用库存, 并计算每行金额."""
        lines: list[tuple[Product, Sku, int, Decimal]] = []
        for requested in request.items:
            sku = await self.skus.get_by_code(requested.sku_code)
            if sku is None or sku.status != "ACTIVE":
                raise ConflictException(
                    message=f"SKU is not available: {requested.sku_code}",
                    code="SKU_NOT_AVAILABLE",
                )
            product = await self.products.get_by_id(sku.product_id)
            if product is None or product.status != "ACTIVE":
                raise ConflictException(
                    message=f"Product is not available: {sku.sku_code}",
                    code="SKU_NOT_AVAILABLE",
                )
            inventory = await self.inventories.get_by_sku_id(sku.id)
            if inventory is None:
                raise ConflictException(
                    message="Inventory not found",
                    code="INSUFFICIENT_STOCK",
                )
            available = inventory.total_quantity - inventory.reserved_quantity
            if available < requested.quantity:
                raise ConflictException(
                    message="Insufficient available inventory",
                    code="INSUFFICIENT_STOCK",
                )
            lines.append(
                (
                    product,
                    sku,
                    requested.quantity,
                    money(sku.price * requested.quantity),
                )
            )
        return lines

    async def create_order(
        self,
        *,
        user_id: int,
        request: OrderCreateRequest,
    ) -> Order:
        """创建订单并原子预占库存.

        Args:
            user_id: 下单用户.
            request: SKU, 数量, 收货信息和幂等键.

        Returns:
            创建后的订单详情.

        Raises:
            ConflictException: SKU 不可用, 库存不足或幂等键参数冲突.
        """
        # ① 先查幂等键; 同一请求重放直接返回旧订单.
        fingerprint = self._fingerprint(request)
        existing = await self._existing_or_conflict(
            user_id=user_id,
            idempotency_key=request.idempotency_key,
            fingerprint=fingerprint,
        )
        if existing is not None:
            return existing

        # ② 校验 SKU/商品并计算快照金额.
        lines = await self._load_purchase_lines(request)
        total_amount = money(sum((line[3] for line in lines), Decimal("0.00")))

        try:
            # ③ 订单, 订单项和库存预占必须处于同一事务.
            async with transaction_context(self.session):
                order = Order(
                    order_no=new_order_no(),
                    user_id=user_id,
                    # Payment is out of scope; an order starts as CREATED.
                    status="CREATED",
                    payment_status="UNPAID",
                    fulfillment_status="UNSHIPPED",
                    total_amount=total_amount,
                    paid_amount=Decimal("0.00"),
                    refunded_amount=Decimal("0.00"),
                    currency="CNY",
                    receiver_name=request.receiver_name,
                    receiver_phone=request.receiver_phone,
                    receiver_address=request.receiver_address,
                    customer_remark=request.customer_remark,
                    idempotency_key=request.idempotency_key,
                    request_fingerprint=fingerprint,
                    # Legacy non-null column; no auto-close job uses it now.
                    expires_at=utc_after(
                        minutes=settings.order_payment_timeout_minutes
                    ),
                )
                await self.orders.create(order)

                created_items = []
                for product, sku, quantity, line_amount in lines:
                    item = await self.items.create(
                        order_id=order.id,
                        product_id=product.id,
                        sku_id=sku.id,
                        product_no=product.product_no,
                        product_name=product.name,
                        sku_code=sku.sku_code,
                        sku_attributes=sku.attributes,
                        currency="CNY",
                        unit_price=money(sku.price),
                        quantity=quantity,
                        line_amount=line_amount,
                    )
                    created_items.append(item)

                for item in sorted(created_items, key=lambda value: value.sku_id):
                    await self.inventory.reserve(
                        sku_id=item.sku_id,
                        quantity=item.quantity,
                        idempotency_key=f"order:{order.id}:line:{item.id}:reserve",
                        business_type="ORDER",
                        business_id=order.id,
                        business_item_id=item.id,
                    )
        except IntegrityError as exc:
            # ④ 并发重放可能同时撞唯一约束, 回滚后按幂等键重新读取.
            await self.session.rollback()
            if not self._is_idempotency_conflict(exc):
                raise
            existing = await self.orders.get_by_user_and_key(
                user_id,
                request.idempotency_key,
            )
            if existing is None:
                raise
            if existing.request_fingerprint != fingerprint:
                raise ConflictException(
                    message="Idempotency key was used with different parameters",
                    code="IDEMPOTENCY_KEY_CONFLICT",
                ) from exc
            return await self._detail(existing.order_no)

        return await self._detail(order.order_no)

    async def get_order(self, *, user_id: int, order_no: str) -> Order:
        """读取当前用户订单, 越权时按不存在处理."""
        order = await self._detail(order_no)
        if order.user_id != user_id:
            raise ResourceNotFoundException(
                message="Order not found",
                code="ORDER_NOT_FOUND",
            )
        return order

    async def list_orders(
        self,
        *,
        user_id: int,
        page: int,
        page_size: int,
        status: str | None = None,
    ) -> tuple[list[Order], int]:
        """分页查询当前用户订单和总数."""
        items = await self.orders.list_for_user(
            user_id,
            page=page,
            page_size=page_size,
            status=status,
        )
        total = await self.orders.count_for_user(user_id, status=status)
        return items, total

    async def list_admin(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
    ) -> tuple[list[Order], int]:
        """管理员分页查询全部订单和总数."""
        items = await self.orders.list_admin(
            page=page,
            page_size=page_size,
            status=status,
        )
        total = await self.orders.count_admin(status=status)
        return items, total

    async def get_order_admin(self, order_no: str) -> Order:
        """管理员读取任意订单详情."""
        return await self._detail(order_no)

    async def _lock_order_for_user(
        self,
        *,
        user_id: int,
        order_no: str,
    ) -> tuple[Order, list]:
        """锁定当前用户订单并读取订单项, 用于状态变更."""
        order = await self.orders.get_by_no(order_no, for_update=True)
        if order is None or order.user_id != user_id:
            raise ResourceNotFoundException(
                message="Order not found",
                code="ORDER_NOT_FOUND",
            )
        return order, await self.items.list_by_order(order.id)

    async def cancel_order(
        self,
        *,
        user_id: int,
        order_no: str,
        reason: str | None = None,
    ) -> Order:
        """取消未发货订单并释放全部库存预占.

        Args:
            user_id: 下单用户.
            order_no: 订单号.
            reason: 可选取消原因.

        Returns:
            状态为 CANCELLED 的订单.
        """
        async with transaction_context(self.session):
            # ① 行锁订单, 并确认订单属于当前用户.
            order, items = await self._lock_order_for_user(
                user_id=user_id,
                order_no=order_no,
            )
            if order.status not in {"CREATED", "PENDING_PAYMENT"}:
                raise ConflictException(
                    message="Only unshipped CREATED orders can be cancelled",
                    code="ORDER_STATUS_CONFLICT",
                )
            # ② 逐行释放预占, 幂等键绑定订单项.
            for item in sorted(items, key=lambda value: value.sku_id):
                await self.inventory.release(
                    sku_id=item.sku_id,
                    quantity=item.quantity,
                    idempotency_key=f"order:{order.id}:line:{item.id}:release",
                    business_type="ORDER",
                    business_id=order.id,
                    business_item_id=item.id,
                )
            order.status = "CANCELLED"
            order.cancelled_at = utc_now()
            order.cancel_reason = reason
            await self.orders.save(order)
        return await self._detail(order_no)

    async def ship(
        self,
        *,
        order_no: str,
        request: ShipOrderRequest,
    ) -> Order:
        """发货: CREATED 订单扣减预占, 历史 PAID 订单不再扣库存."""
        async with transaction_context(self.session):
            order = await self.orders.get_by_no(order_no, for_update=True)
            if order is None:
                raise ResourceNotFoundException(
                    message="Order not found",
                    code="ORDER_NOT_FOUND",
                )
            if (
                order.status not in LEGACY_SHIPPABLE_STATUSES
                or order.fulfillment_status != "UNSHIPPED"
            ):
                raise ConflictException(
                    message="Order cannot be shipped in its current state",
                    code="ORDER_STATUS_CONFLICT",
                )
            items = await self.items.list_by_order(order.id)
            # New CREATED orders still hold a reservation. Legacy PAID orders
            # already deducted stock during the retired payment flow.
            if order.status == "CREATED":
                for item in sorted(items, key=lambda value: value.sku_id):
                    await self.inventory.deduct_reserved(
                        sku_id=item.sku_id,
                        quantity=item.quantity,
                        idempotency_key=f"order:{order.id}:line:{item.id}:ship",
                        business_type="ORDER",
                        business_id=order.id,
                        business_item_id=item.id,
                    )
            order.fulfillment_status = "SHIPPED"
            order.shipping_carrier = request.shipping_carrier
            order.tracking_no = request.tracking_no
            order.shipped_at = utc_now()
            await self.orders.save(order)
        return await self._detail(order_no)

    async def deliver(self, *, order_no: str) -> Order:
        """把已发货订单标记为已送达; 送达后才允许申请换货."""
        async with transaction_context(self.session):
            order = await self.orders.get_by_no(order_no, for_update=True)
            if order is None:
                raise ResourceNotFoundException(
                    message="Order not found",
                    code="ORDER_NOT_FOUND",
                )
            if (
                order.status not in LEGACY_SHIPPABLE_STATUSES
                or order.fulfillment_status != "SHIPPED"
            ):
                raise ConflictException(
                    message="Order cannot be delivered in its current state",
                    code="ORDER_STATUS_CONFLICT",
                )
            order.fulfillment_status = "DELIVERED"
            order.delivered_at = utc_now()
            await self.orders.save(order)
        return await self._detail(order_no)

    async def complete(self, *, order_no: str) -> Order:
        """把已送达订单标记为完成, 订单和履约状态同时变为 COMPLETED."""
        async with transaction_context(self.session):
            order = await self.orders.get_by_no(order_no, for_update=True)
            if order is None:
                raise ResourceNotFoundException(
                    message="Order not found",
                    code="ORDER_NOT_FOUND",
                )
            if (
                order.status not in LEGACY_SHIPPABLE_STATUSES
                or order.fulfillment_status != "DELIVERED"
            ):
                raise ConflictException(
                    message="Order cannot be completed in its current state",
                    code="ORDER_STATUS_CONFLICT",
                )
            order.status = "COMPLETED"
            order.fulfillment_status = "COMPLETED"
            order.completed_at = utc_now()
            await self.orders.save(order)
        return await self._detail(order_no)
