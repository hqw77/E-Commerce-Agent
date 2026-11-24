"""Simplified after-sales workflow.

Only EXCHANGE remains in the current scope. REFUND_ONLY and RETURN_REFUND are
historical types: existing rows remain readable, but no new request can use
them and no fund movement is ever executed.
"""

from datetime import timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ConflictException, ResourceNotFoundException
from app.models.after_sale import AfterSale
from app.models.order import Order
from app.models.order_item import OrderItem
from app.repositories.after_sale import (
    ACTIVE_AFTER_SALE_STATUSES,
    AfterSaleRepository,
)
from app.repositories.order import OrderRepository
from app.repositories.order_item import OrderItemRepository
from app.schemas.after_sale import (
    AfterSaleApplyRequest,
    CompleteExchangeRequest,
    ReturnShipmentRequest,
)
from app.services.inventory import InventoryService
from app.services.transaction import transaction_context
from app.utils.order import new_after_sales_no, utc_now

CURRENT_AFTER_SALE_TYPE = "EXCHANGE"


class AfterSaleService:
    """Application, review and exchange workflow without payment/refunds."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.after_sales = AfterSaleRepository(session)
        self.orders = OrderRepository(session)
        self.items = OrderItemRepository(session)
        self.inventory = InventoryService(session)

    @staticmethod
    def _fingerprint(
        *,
        request: AfterSaleApplyRequest,
        item: OrderItem,
    ) -> tuple[int, Decimal]:
        return item.quantity, item.line_amount

    async def _detail(self, after_sales_no: str) -> AfterSale:
        after_sale = await self.after_sales.get_by_no(after_sales_no)
        if after_sale is None:
            raise ResourceNotFoundException(
                message="After-sales record not found",
                code="AFTER_SALES_NOT_FOUND",
            )
        return after_sale

    async def _get_locked(
        self,
        *,
        after_sales_no: str,
    ) -> tuple[AfterSale, Order, OrderItem]:
        # Lock in the stable order -> item -> after-sales order.
        after_sale = await self.after_sales.get_by_no(after_sales_no)
        if after_sale is None:
            raise ResourceNotFoundException(
                message="After-sales record not found",
                code="AFTER_SALES_NOT_FOUND",
            )
        order = await self.orders.get_by_id(
            after_sale.order_id,
            for_update=True,
        )
        item = await self.items.get_by_id(
            after_sale.order_item_id,
            for_update=True,
        )
        if order is None or item is None:
            raise ResourceNotFoundException(
                message="After-sales order data not found",
                code="AFTER_SALES_NOT_FOUND",
            )
        after_sale = await self.after_sales.get_by_no(
            after_sales_no,
            for_update=True,
        )
        if after_sale is None:
            raise ResourceNotFoundException(
                message="After-sales record not found",
                code="AFTER_SALES_NOT_FOUND",
            )
        return after_sale, order, item

    @staticmethod
    def _check_window(*, order: Order) -> None:
        base = order.delivered_at
        if base is None:
            raise ConflictException(
                message="Exchange requires a delivered order",
                code="AFTER_SALES_NOT_ALLOWED",
            )
        deadline = base + timedelta(hours=settings.after_sales_window_hours)
        if utc_now() > deadline:
            raise ConflictException(
                message="After-sales application window has expired",
                code="AFTER_SALES_EXPIRED",
            )

    async def apply(
        self,
        *,
        user_id: int,
        order_no: str,
        request: AfterSaleApplyRequest,
    ) -> AfterSale:
        if request.type != CURRENT_AFTER_SALE_TYPE:
            raise ConflictException(
                message="Only EXCHANGE after-sales is available; refunds are out of scope",
                code="AFTER_SALE_TYPE_REMOVED",
            )

        async with transaction_context(self.session):
            order = await self.orders.get_by_no(order_no, for_update=True)
            if order is None or order.user_id != user_id:
                raise ResourceNotFoundException(
                    message="Order not found",
                    code="ORDER_NOT_FOUND",
                )
            item = await self.items.get_by_order_and_sku(
                order.id,
                request.sku_code,
                for_update=True,
            )
            if item is None:
                raise ResourceNotFoundException(
                    message="Order item not found",
                    code="ORDER_ITEM_NOT_FOUND",
                )

            existing = await self.after_sales.get_by_user_and_key(
                user_id,
                request.idempotency_key,
                for_update=True,
            )
            if existing is not None:
                if AfterSaleRepository.same_fingerprint(
                    existing,
                    order_id=order.id,
                    order_item_id=item.id,
                    type=request.type,
                    quantity=item.quantity,
                    requested_amount=item.line_amount,
                    reason=request.reason,
                    description=request.description,
                    evidence_urls=request.evidence_urls,
                ):
                    return existing
                raise ConflictException(
                    message="Idempotency key was used with different parameters",
                    code="IDEMPOTENCY_KEY_CONFLICT",
                )

            active = await self.after_sales.get_active_for_item(
                item.id,
                for_update=True,
            )
            if active is not None:
                raise ConflictException(
                    message="An active after-sales request already exists",
                    code="AFTER_SALES_ALREADY_EXISTS",
                )

            if order.fulfillment_status != "DELIVERED":
                raise ConflictException(
                    message="Exchange requires a delivered order",
                    code="AFTER_SALES_NOT_ALLOWED",
                )
            self._check_window(order=order)

            after_sale = AfterSale(
                after_sales_no=new_after_sales_no(),
                order_id=order.id,
                order_item_id=item.id,
                user_id=user_id,
                type=request.type,
                status="PENDING_REVIEW",
                quantity=item.quantity,
                # Kept for schema compatibility; it is not a fund refund.
                requested_amount=item.line_amount,
                reason=request.reason,
                description=request.description,
                evidence_urls=request.evidence_urls,
                idempotency_key=request.idempotency_key,
            )
            await self.after_sales.create(after_sale)
        return await self._detail(after_sale.after_sales_no)

    async def get_for_user(
        self,
        *,
        user_id: int,
        after_sales_no: str,
    ) -> AfterSale:
        after_sale = await self._detail(after_sales_no)
        if after_sale.user_id != user_id:
            raise ResourceNotFoundException(
                message="After-sales record not found",
                code="AFTER_SALES_NOT_FOUND",
            )
        return after_sale

    async def get_with_relations_for_user(
        self,
        *,
        user_id: int,
        after_sales_no: str,
    ) -> tuple[AfterSale, Order, OrderItem]:
        after_sale = await self.get_for_user(
            user_id=user_id,
            after_sales_no=after_sales_no,
        )
        order = await self.orders.get_by_id(after_sale.order_id)
        item = await self.items.get_by_id(after_sale.order_item_id)
        if order is None or item is None:
            raise ResourceNotFoundException(
                message="After-sales record not found",
                code="AFTER_SALES_NOT_FOUND",
            )
        return after_sale, order, item

    async def list_for_order_for_user(
        self,
        *,
        user_id: int,
        order_no: str,
        page: int,
        page_size: int,
    ) -> tuple[list[AfterSale], int]:
        order = await self.orders.get_by_no(order_no)
        if order is None or order.user_id != user_id:
            raise ResourceNotFoundException(
                message="Order not found",
                code="ORDER_NOT_FOUND",
            )
        items = await self.after_sales.list_for_order(order.id)
        start = (page - 1) * page_size
        return items[start : start + page_size], len(items)

    async def list_for_user(
        self,
        *,
        user_id: int,
        page: int,
        page_size: int,
    ) -> tuple[list[AfterSale], int]:
        items = await self.after_sales.list_for_user(
            user_id,
            page=page,
            page_size=page_size,
        )
        total = await self.after_sales.count_for_user(user_id)
        return items, total

    async def list_admin(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
    ) -> tuple[list[AfterSale], int]:
        items = await self.after_sales.list_admin(
            page=page,
            page_size=page_size,
            status=status,
        )
        total = await self.after_sales.count_admin(status=status)
        return items, total

    async def get_admin(self, after_sales_no: str) -> AfterSale:
        return await self._detail(after_sales_no)

    async def cancel(
        self,
        *,
        user_id: int,
        after_sales_no: str,
    ) -> AfterSale:
        async with transaction_context(self.session):
            after_sale, _order, _item = await self._get_locked(
                after_sales_no=after_sales_no
            )
            if after_sale.user_id != user_id:
                raise ResourceNotFoundException(
                    message="After-sales record not found",
                    code="AFTER_SALES_NOT_FOUND",
                )
            if after_sale.status != "PENDING_REVIEW":
                raise ConflictException(
                    message="Only pending review requests can be cancelled",
                    code="AFTER_SALES_STATUS_CONFLICT",
                )
            after_sale.status = "CANCELLED"
            after_sale.cancelled_at = utc_now()
            await self.after_sales.save(after_sale)
        return await self._detail(after_sales_no)

    async def approve(
        self,
        *,
        after_sales_no: str,
        admin_id: int,
        review_note: str | None,
    ) -> AfterSale:
        async with transaction_context(self.session):
            after_sale, _order, _item = await self._get_locked(
                after_sales_no=after_sales_no
            )
            if after_sale.status != "PENDING_REVIEW":
                raise ConflictException(
                    message="Only pending review requests can be approved",
                    code="AFTER_SALES_STATUS_CONFLICT",
                )
            if after_sale.type != CURRENT_AFTER_SALE_TYPE:
                raise ConflictException(
                    message="Only EXCHANGE after-sales is supported",
                    code="AFTER_SALE_TYPE_REMOVED",
                )
            after_sale.approved_amount = None
            after_sale.review_note = review_note
            after_sale.reviewed_by = admin_id
            after_sale.reviewed_at = utc_now()
            after_sale.status = "WAITING_RETURN"
            await self.after_sales.save(after_sale)
        return await self._detail(after_sales_no)

    async def reject(
        self,
        *,
        after_sales_no: str,
        admin_id: int,
        review_note: str,
    ) -> AfterSale:
        async with transaction_context(self.session):
            after_sale, _order, _item = await self._get_locked(
                after_sales_no=after_sales_no
            )
            if after_sale.status != "PENDING_REVIEW":
                raise ConflictException(
                    message="Only pending review requests can be rejected",
                    code="AFTER_SALES_STATUS_CONFLICT",
                )
            after_sale.status = "REJECTED"
            after_sale.review_note = review_note
            after_sale.reviewed_by = admin_id
            after_sale.reviewed_at = utc_now()
            await self.after_sales.save(after_sale)
        return await self._detail(after_sales_no)

    async def submit_return_shipment(
        self,
        *,
        user_id: int,
        after_sales_no: str,
        request: ReturnShipmentRequest,
    ) -> AfterSale:
        async with transaction_context(self.session):
            after_sale, _order, _item = await self._get_locked(
                after_sales_no=after_sales_no
            )
            if after_sale.user_id != user_id:
                raise ResourceNotFoundException(
                    message="After-sales record not found",
                    code="AFTER_SALES_NOT_FOUND",
                )
            if after_sale.status != "WAITING_RETURN":
                raise ConflictException(
                    message="Return shipment is not allowed in current state",
                    code="RETURN_NOT_ALLOWED",
                )
            after_sale.status = "RETURN_SHIPPED"
            after_sale.return_carrier = request.return_carrier
            after_sale.return_tracking_no = request.return_tracking_no
            after_sale.returned_at = utc_now()
            await self.after_sales.save(after_sale)
        return await self._detail(after_sales_no)

    async def receive(
        self,
        *,
        after_sales_no: str,
        admin_id: int,
    ) -> AfterSale:
        async with transaction_context(self.session):
            after_sale, _order, item = await self._get_locked(
                after_sales_no=after_sales_no
            )
            if after_sale.status != "RETURN_SHIPPED":
                raise ConflictException(
                    message="Only shipped returns can be received",
                    code="AFTER_SALES_STATUS_CONFLICT",
                )
            after_sale.received_by = admin_id
            after_sale.received_at = utc_now()
            await self.inventory.restock(
                sku_id=item.sku_id,
                quantity=item.quantity,
                idempotency_key=f"after_sale:{after_sale.id}:return-restock",
                business_type="AFTER_SALE",
                business_id=after_sale.id,
                business_item_id=item.id,
            )
            after_sale.status = "RECEIVED"
            await self.after_sales.save(after_sale)
        return await self._detail(after_sales_no)

    async def complete_exchange(
        self,
        *,
        after_sales_no: str,
        request: CompleteExchangeRequest,
    ) -> AfterSale:
        async with transaction_context(self.session):
            after_sale, _order, item = await self._get_locked(
                after_sales_no=after_sales_no
            )
            if after_sale.status != "RECEIVED" or after_sale.type != "EXCHANGE":
                raise ConflictException(
                    message="Exchange cannot be completed in current state",
                    code="AFTER_SALES_STATUS_CONFLICT",
                )
            await self.inventory.direct_outbound_for_business(
                sku_id=item.sku_id,
                quantity=item.quantity,
                idempotency_key=f"after_sale:{after_sale.id}:exchange-outbound",
                business_type="AFTER_SALE",
                business_id=after_sale.id,
                business_item_id=item.id,
            )
            after_sale.status = "COMPLETED"
            after_sale.replacement_carrier = request.replacement_carrier
            after_sale.replacement_tracking_no = request.replacement_tracking_no
            after_sale.replacement_shipped_at = utc_now()
            after_sale.completed_at = utc_now()
            await self.after_sales.save(after_sale)
        return await self._detail(after_sales_no)


ACTIVE_STATUSES = ACTIVE_AFTER_SALE_STATUSES
