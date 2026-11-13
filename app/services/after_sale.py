from datetime import timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    ConflictException,
    ResourceNotFoundException,
)
from app.models.after_sale import AfterSale
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.payment import Payment
from app.repositories.after_sale import (
    ACTIVE_AFTER_SALE_STATUSES,
    AfterSaleRepository,
)
from app.repositories.order import OrderRepository
from app.repositories.order_item import OrderItemRepository
from app.repositories.payment import PaymentRepository
from app.schemas.after_sale import (
    AfterSaleApplyRequest,
    CompleteExchangeRequest,
    ReturnShipmentRequest,
)
from app.services.inventory import InventoryService
from app.services.refund import RefundService
from app.services.transaction import transaction_context
from app.utils.order import new_after_sales_no, utc_now


class AfterSaleService:
    """After-sales application, review and return/exchange workflow."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.after_sales = AfterSaleRepository(session)
        self.orders = OrderRepository(session)
        self.items = OrderItemRepository(session)
        self.payments = PaymentRepository(session)
        self.inventory = InventoryService(session)
        self.refunds = RefundService(session)

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
        lock_payment: bool = False,
    ) -> tuple[AfterSale, Order, OrderItem, Payment | None]:
        # Discover the relation without holding a lock, then acquire locks in
        # the global order: order -> item -> payment -> after-sales.
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
        payment = None
        if lock_payment:
            payment = await self.payments.get_by_order(
                order.id,
                for_update=True,
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
        return after_sale, order, item, payment

    @staticmethod
    def _check_window(
        *,
        after_sale_type: str,
        order: Order,
    ) -> None:
        base = order.paid_at if after_sale_type == "REFUND_ONLY" else order.delivered_at
        if base is None:
            raise ConflictException(
                message="After-sales time base is not available",
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

            if order.payment_status not in {"PAID", "PARTIALLY_REFUNDED"}:
                raise ConflictException(
                    message="Order is not eligible for after-sales",
                    code="AFTER_SALES_NOT_ALLOWED",
                )
            if request.type == "REFUND_ONLY":
                if order.fulfillment_status != "UNSHIPPED":
                    raise ConflictException(
                        message="Refund-only requires an unshipped order",
                        code="AFTER_SALES_NOT_ALLOWED",
                    )
            elif order.fulfillment_status != "DELIVERED":
                raise ConflictException(
                    message="Return or exchange requires a delivered order",
                    code="AFTER_SALES_NOT_ALLOWED",
                )

            self._check_window(
                after_sale_type=request.type,
                order=order,
            )

            after_sale = AfterSale(
                after_sales_no=new_after_sales_no(),
                order_id=order.id,
                order_item_id=item.id,
                user_id=user_id,
                type=request.type,
                status="PENDING_REVIEW",
                quantity=item.quantity,
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
            after_sale, _order, _item, _payment = await self._get_locked(
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
        refund = None
        async with transaction_context(self.session):
            after_sale, order, _item, payment = await self._get_locked(
                after_sales_no=after_sales_no,
                lock_payment=True,
            )
            if after_sale.status != "PENDING_REVIEW":
                raise ConflictException(
                    message="Only pending review requests can be approved",
                    code="AFTER_SALES_STATUS_CONFLICT",
                )
            if payment is None or payment.status not in {
                "SUCCESS",
                "PARTIALLY_REFUNDED",
            }:
                raise ConflictException(
                    message="Order payment is not refundable",
                    code="REFUND_NOT_ALLOWED",
                )

            after_sale.approved_amount = after_sale.requested_amount
            after_sale.review_note = review_note
            after_sale.reviewed_by = admin_id
            after_sale.reviewed_at = utc_now()

            if after_sale.type == "REFUND_ONLY":
                after_sale.status = "REFUNDING"
                refund = await self.refunds.create_for_after_sale_locked(
                    order=order,
                    payment=payment,
                    after_sale=after_sale,
                    amount=after_sale.approved_amount,
                    idempotency_key=f"after-sale:{after_sale.id}:refund",
                )
                if refund.channel == "MOCK":
                    await self.refunds.settle_locked(
                        refund=refund,
                        order=order,
                        payment=payment,
                        after_sale=after_sale,
                        restock=True,
                    )
                else:
                    after_sale.status = "REFUNDING"
            else:
                after_sale.status = "WAITING_RETURN"

            await self.after_sales.save(after_sale)

        if refund is not None and refund.channel == "ALIPAY":
            await self.refunds.process_alipay_refund(refund_no=refund.refund_no)
        return await self._detail(after_sales_no)

    async def reject(
        self,
        *,
        after_sales_no: str,
        admin_id: int,
        review_note: str,
    ) -> AfterSale:
        async with transaction_context(self.session):
            after_sale, _order, _item, _payment = await self._get_locked(
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
            after_sale, _order, _item, _payment = await self._get_locked(
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
            after_sale, order, item, payment = await self._get_locked(
                after_sales_no=after_sales_no,
                lock_payment=True,
            )
            if after_sale.status != "RETURN_SHIPPED":
                raise ConflictException(
                    message="Only shipped returns can be received",
                    code="AFTER_SALES_STATUS_CONFLICT",
                )
            if payment is None:
                raise ResourceNotFoundException(
                    message="Payment not found",
                    code="PAYMENT_NOT_FOUND",
                )

            after_sale.received_by = admin_id
            after_sale.received_at = utc_now()

            refund = None
            if after_sale.type == "RETURN_REFUND":
                after_sale.status = "REFUNDING"
                refund = await self.refunds.create_for_after_sale_locked(
                    order=order,
                    payment=payment,
                    after_sale=after_sale,
                    amount=after_sale.requested_amount,
                    idempotency_key=f"after-sale:{after_sale.id}:refund",
                )

            await self.inventory.restock(
                sku_id=item.sku_id,
                quantity=item.quantity,
                idempotency_key=(f"after_sale:{after_sale.id}:return-restock"),
                business_type="AFTER_SALE",
                business_id=after_sale.id,
                business_item_id=item.id,
            )

            if after_sale.type == "RETURN_REFUND" and refund is not None:
                if refund.channel == "MOCK":
                    await self.refunds.settle_locked(
                        refund=refund,
                        order=order,
                        payment=payment,
                        after_sale=after_sale,
                        restock=False,
                    )
            elif after_sale.type == "EXCHANGE":
                after_sale.status = "RECEIVED"

            await self.after_sales.save(after_sale)

        if refund is not None and refund.channel == "ALIPAY":
            await self.refunds.process_alipay_refund(refund_no=refund.refund_no)
        return await self._detail(after_sales_no)

    async def complete_exchange(
        self,
        *,
        after_sales_no: str,
        request: CompleteExchangeRequest,
    ) -> AfterSale:
        async with transaction_context(self.session):
            after_sale, _order, item, _payment = await self._get_locked(
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
                idempotency_key=(f"after_sale:{after_sale.id}:exchange-outbound"),
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
