from decimal import Decimal

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    ConflictException,
    ResourceNotFoundException,
)
from app.core.logging import get_logger
from app.models.order import Order
from app.models.payment import Payment
from app.models.product import Product
from app.models.sku import Sku
from app.repositories.inventory import InventoryRepository
from app.repositories.order import OrderRepository
from app.repositories.order_item import OrderItemRepository
from app.repositories.payment import PaymentRepository
from app.repositories.product import ProductRepository
from app.repositories.sku import SkuRepository
from app.schemas.order import OrderCreateRequest, ShipOrderRequest
from app.services.alipay import AlipayClient, AlipayConfigurationError
from app.services.inventory import InventoryService
from app.services.transaction import transaction_context
from app.utils.order import (
    money,
    new_order_no,
    request_fingerprint,
    utc_after,
    utc_now,
)

logger = get_logger(__name__)


class OrderService:
    """Order creation, cancellation and fulfillment rules."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.orders = OrderRepository(session)
        self.items = OrderItemRepository(session)
        self.payments = PaymentRepository(session)
        self.products = ProductRepository(session)
        self.skus = SkuRepository(session)
        self.inventories = InventoryRepository(session)
        self.inventory = InventoryService(session)

    @staticmethod
    def _fingerprint(request: OrderCreateRequest) -> str:
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
        return "uq_orders_user_idempotency" in str(exc.orig)

    async def _detail(self, order_no: str) -> Order:
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
        fingerprint = self._fingerprint(request)
        existing = await self._existing_or_conflict(
            user_id=user_id,
            idempotency_key=request.idempotency_key,
            fingerprint=fingerprint,
        )
        if existing is not None:
            return existing

        lines = await self._load_purchase_lines(request)
        total_amount = money(sum((line[3] for line in lines), Decimal("0.00")))

        try:
            async with transaction_context(self.session):
                order = Order(
                    order_no=new_order_no(),
                    user_id=user_id,
                    status="PENDING_PAYMENT",
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
                        idempotency_key=(f"order:{order.id}:line:{item.id}:reserve"),
                        business_type="ORDER",
                        business_id=order.id,
                        business_item_id=item.id,
                    )
        except IntegrityError as exc:
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
        items = await self.orders.list_admin(
            page=page,
            page_size=page_size,
            status=status,
        )
        total = await self.orders.count_admin(status=status)
        return items, total

    async def get_order_admin(self, order_no: str) -> Order:
        return await self._detail(order_no)

    async def _lock_order_for_user(
        self,
        *,
        user_id: int,
        order_no: str,
    ) -> tuple[Order, list]:
        order = await self.orders.get_by_no(order_no, for_update=True)
        if order is None or order.user_id != user_id:
            raise ResourceNotFoundException(
                message="Order not found",
                code="ORDER_NOT_FOUND",
            )
        items = await self.items.list_by_order(order.id)
        return order, items

    async def _close_alipay_best_effort(self, payment: Payment | None) -> None:
        if payment is None or payment.channel != "ALIPAY":
            return
        client = AlipayClient()
        if not client.configured:
            return
        try:
            await client.close_trade(out_trade_no=payment.payment_no)
        except (httpx.HTTPError, AlipayConfigurationError, ValueError):
            logger.warning(
                "alipay_close_failed",
                payment_no=payment.payment_no,
            )

    async def cancel_order(
        self,
        *,
        user_id: int,
        order_no: str,
        reason: str | None = None,
    ) -> Order:
        async with transaction_context(self.session):
            order, items = await self._lock_order_for_user(
                user_id=user_id,
                order_no=order_no,
            )
            if order.status != "PENDING_PAYMENT":
                raise ConflictException(
                    message="Only pending-payment orders can be cancelled",
                    code="ORDER_STATUS_CONFLICT",
                )

            payment = await self.payments.get_by_order(
                order.id,
                for_update=True,
            )
            for item in sorted(items, key=lambda value: value.sku_id):
                await self.inventory.release(
                    sku_id=item.sku_id,
                    quantity=item.quantity,
                    idempotency_key=f"order:{order.id}:line:{item.id}:release",
                    business_type="ORDER",
                    business_id=order.id,
                    business_item_id=item.id,
                )

            if payment is not None and payment.status == "PENDING":
                payment.status = "CLOSED"
                payment.closed_at = utc_now()
                await self.payments.save(payment)

            order.status = "CANCELLED"
            order.cancelled_at = utc_now()
            order.cancel_reason = reason
            await self.orders.save(order)

        await self._close_alipay_best_effort(payment)
        return await self._detail(order_no)

    async def close_expired_orders(self) -> int:
        expired = await self.orders.list_expired_pending()
        closed = 0
        for candidate in expired:
            try:
                async with transaction_context(self.session):
                    order = await self.orders.get_by_id(
                        candidate.id,
                        for_update=True,
                    )
                    if (
                        order is None
                        or order.status != "PENDING_PAYMENT"
                        or order.expires_at > utc_now()
                    ):
                        continue
                    items = await self.items.list_by_order(order.id)
                    payment = await self.payments.get_by_order(
                        order.id,
                        for_update=True,
                    )
                    for item in sorted(items, key=lambda value: value.sku_id):
                        await self.inventory.release(
                            sku_id=item.sku_id,
                            quantity=item.quantity,
                            idempotency_key=(
                                f"order:{order.id}:line:{item.id}:release"
                            ),
                            business_type="ORDER",
                            business_id=order.id,
                            business_item_id=item.id,
                        )
                    if payment is not None and payment.status == "PENDING":
                        payment.status = "CLOSED"
                        payment.closed_at = utc_now()
                        await self.payments.save(payment)
                    order.status = "CLOSED"
                    order.closed_at = utc_now()
                    order.close_reason = "PAYMENT_TIMEOUT"
                    await self.orders.save(order)
                closed += 1
            except ConflictException:
                await self.session.rollback()
                continue
        return closed

    async def ship(
        self,
        *,
        order_no: str,
        request: ShipOrderRequest,
    ) -> Order:
        async with transaction_context(self.session):
            order = await self.orders.get_by_no(order_no, for_update=True)
            if order is None:
                raise ResourceNotFoundException(
                    message="Order not found",
                    code="ORDER_NOT_FOUND",
                )
            if order.status != "PAID" or order.fulfillment_status != "UNSHIPPED":
                raise ConflictException(
                    message="Order cannot be shipped in its current state",
                    code="ORDER_STATUS_CONFLICT",
                )
            order.fulfillment_status = "SHIPPED"
            order.shipping_carrier = request.shipping_carrier
            order.tracking_no = request.tracking_no
            order.shipped_at = utc_now()
            await self.orders.save(order)
        return await self._detail(order_no)

    async def deliver(self, *, order_no: str) -> Order:
        async with transaction_context(self.session):
            order = await self.orders.get_by_no(order_no, for_update=True)
            if order is None:
                raise ResourceNotFoundException(
                    message="Order not found",
                    code="ORDER_NOT_FOUND",
                )
            if order.status != "PAID" or order.fulfillment_status != "SHIPPED":
                raise ConflictException(
                    message="Order cannot be delivered in its current state",
                    code="ORDER_STATUS_CONFLICT",
                )
            order.fulfillment_status = "DELIVERED"
            order.delivered_at = utc_now()
            await self.orders.save(order)
        return await self._detail(order_no)

    async def complete(self, *, order_no: str) -> Order:
        async with transaction_context(self.session):
            order = await self.orders.get_by_no(order_no, for_update=True)
            if order is None:
                raise ResourceNotFoundException(
                    message="Order not found",
                    code="ORDER_NOT_FOUND",
                )
            if order.status != "PAID" or order.fulfillment_status != "DELIVERED":
                raise ConflictException(
                    message="Order cannot be completed in its current state",
                    code="ORDER_STATUS_CONFLICT",
                )
            order.status = "COMPLETED"
            order.fulfillment_status = "COMPLETED"
            order.completed_at = utc_now()
            await self.orders.save(order)
        return await self._detail(order_no)
