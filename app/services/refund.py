from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictException,
    ResourceNotFoundException,
)
from app.models.after_sale import AfterSale
from app.models.order import Order
from app.models.payment import Payment
from app.models.refund import Refund
from app.repositories.inventory import InventoryRepository
from app.repositories.order import OrderRepository
from app.repositories.order_item import OrderItemRepository
from app.repositories.payment import PaymentRepository
from app.repositories.refund import RefundRepository
from app.schemas.payment import ManualRefundRequest
from app.services.inventory import InventoryService
from app.services.transaction import transaction_context
from app.utils.order import new_refund_no, utc_now


class RefundService:
    """Refund amount validation and refund state transitions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.orders = OrderRepository(session)
        self.items = OrderItemRepository(session)
        self.payments = PaymentRepository(session)
        self.refunds = RefundRepository(session)
        self.inventories = InventoryRepository(session)
        self.inventory = InventoryService(session)

    async def _detail(self, refund_no: str) -> Refund:
        refund = await self.refunds.get_by_no(refund_no)
        if refund is None:
            raise ResourceNotFoundException(
                message="Refund not found",
                code="REFUND_NOT_FOUND",
            )
        return refund

    async def _check_amount(
        self,
        *,
        payment: Payment,
        amount: Decimal,
    ) -> None:
        occupied = await self.refunds.occupied_amount(payment.id)
        if occupied + amount > payment.amount:
            raise ConflictException(
                message="Refund amount exceeds available payment amount",
                code="REFUND_AMOUNT_EXCEEDED",
            )

    async def _create_locked(
        self,
        *,
        order: Order,
        payment: Payment,
        amount: Decimal,
        reason: str,
        idempotency_key: str,
        after_sale: AfterSale | None,
    ) -> Refund:
        existing = await self.refunds.get_by_payment_and_key(
            payment.id,
            idempotency_key,
            for_update=True,
        )
        if existing is not None:
            if (
                existing.amount != amount
                or existing.reason != reason
                or existing.after_sales_id
                != (after_sale.id if after_sale is not None else None)
            ):
                raise ConflictException(
                    message="Idempotency key was used with different parameters",
                    code="IDEMPOTENCY_KEY_CONFLICT",
                )
            return existing

        if after_sale is not None:
            existing_after_sale = await self.refunds.get_by_after_sale(after_sale.id)
            if existing_after_sale is not None:
                return existing_after_sale

        await self._check_amount(payment=payment, amount=amount)
        refund = Refund(
            refund_no=new_refund_no(),
            order_id=order.id,
            payment_id=payment.id,
            after_sales_id=after_sale.id if after_sale is not None else None,
            user_id=order.user_id,
            amount=amount,
            reason=reason,
            channel=payment.channel,
            status="PENDING",
            idempotency_key=idempotency_key,
            requested_at=utc_now(),
        )
        return await self.refunds.create(refund)

    async def create_for_after_sale_locked(
        self,
        *,
        order: Order,
        payment: Payment,
        after_sale: AfterSale,
        amount: Decimal,
        idempotency_key: str,
    ) -> Refund:
        """Create a refund under the caller's order/payment locks."""
        return await self._create_locked(
            order=order,
            payment=payment,
            amount=amount,
            reason=f"AFTER_SALE:{after_sale.type}",
            idempotency_key=idempotency_key,
            after_sale=after_sale,
        )

    async def settle_locked(
        self,
        *,
        refund: Refund,
        order: Order,
        payment: Payment,
        after_sale: AfterSale | None = None,
        restock: bool,
    ) -> Refund:
        """Mark a refund successful under the caller's locks."""
        if refund.status == "SUCCESS":
            return refund

        if refund.status not in {"PENDING", "PROCESSING", "FAILED"}:
            raise ConflictException(
                message="Refund cannot be settled in its current state",
                code="REFUND_STATUS_CONFLICT",
            )

        refund.status = "SUCCESS"
        refund.processed_at = utc_now()
        if refund.failure_code:
            refund.failure_code = None
            refund.failure_message = None

        payment.refunded_amount = payment.refunded_amount + refund.amount
        order.refunded_amount = order.refunded_amount + refund.amount
        if payment.refunded_amount >= payment.amount:
            payment.status = "REFUNDED"
            order.payment_status = "REFUNDED"
        else:
            payment.status = "PARTIALLY_REFUNDED"
            order.payment_status = "PARTIALLY_REFUNDED"

        if (
            restock
            and order.status == "PAID"
            and order.fulfillment_status == "UNSHIPPED"
        ):
            if after_sale is not None and after_sale.type == "REFUND_ONLY":
                item = await self.items.get_by_id(after_sale.order_item_id)
                if item is not None:
                    await self.inventory.restock(
                        sku_id=item.sku_id,
                        quantity=item.quantity,
                        idempotency_key=(f"refund:{refund.id}:restock:{item.id}"),
                        business_type="REFUND",
                        business_id=refund.id,
                        business_item_id=item.id,
                    )
            elif after_sale is None and refund.amount == payment.amount:
                items = await self.items.list_by_order(order.id)
                for item in sorted(items, key=lambda value: value.sku_id):
                    await self.inventory.restock(
                        sku_id=item.sku_id,
                        quantity=item.quantity,
                        idempotency_key=(f"refund:{refund.id}:restock:{item.id}"),
                        business_type="REFUND",
                        business_id=refund.id,
                        business_item_id=item.id,
                    )

        if after_sale is not None:
            after_sale.status = "COMPLETED"
            after_sale.completed_at = utc_now()

        await self.refunds.save(refund)
        await self.payments.save(payment)
        await self.orders.save(order)
        return refund

    async def manual_refund(
        self,
        *,
        request: ManualRefundRequest,
    ) -> Refund:
        async with transaction_context(self.session):
            payment = await self.payments.get_by_no(request.payment_no)
            if payment is None:
                raise ResourceNotFoundException(
                    message="Payment not found",
                    code="PAYMENT_NOT_FOUND",
                )
            order = await self.orders.get_by_id(
                payment.order_id,
                for_update=True,
            )
            if order is None:
                raise ResourceNotFoundException(
                    message="Order not found",
                    code="ORDER_NOT_FOUND",
                )
            payment = await self.payments.get_by_no(
                request.payment_no,
                for_update=True,
            )
            if payment is None:
                raise ResourceNotFoundException(
                    message="Payment not found",
                    code="PAYMENT_NOT_FOUND",
                )
            if payment.status not in {
                "SUCCESS",
                "PARTIALLY_REFUNDED",
                "REFUNDED",
            }:
                raise ConflictException(
                    message="Only successful payments can be refunded",
                    code="REFUND_NOT_ALLOWED",
                )
            refund = await self._create_locked(
                order=order,
                payment=payment,
                amount=request.amount,
                reason=request.reason,
                idempotency_key=request.idempotency_key,
                after_sale=None,
            )
            if refund.status == "PENDING" and refund.channel == "MOCK":
                restock = (
                    order.status == "PAID" and order.fulfillment_status == "UNSHIPPED"
                )
                await self.settle_locked(
                    refund=refund,
                    order=order,
                    payment=payment,
                    restock=restock,
                )
        return await self._detail(refund.refund_no)

    async def get_refund(self, refund_no: str) -> Refund:
        return await self._detail(refund_no)

    async def list_refunds(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
    ) -> tuple[list[Refund], int]:
        items = await self.refunds.list_admin(
            page=page,
            page_size=page_size,
            status=status,
        )
        total = await self.refunds.count_admin(status=status)
        return items, total

    async def retry(self, *, refund_no: str) -> Refund:
        async with transaction_context(self.session):
            refund = await self.refunds.get_by_no(refund_no)
            if refund is None:
                raise ResourceNotFoundException(
                    message="Refund not found",
                    code="REFUND_NOT_FOUND",
                )
            if refund.status not in {"FAILED", "PENDING"}:
                raise ConflictException(
                    message="Only failed or pending refunds can be retried",
                    code="REFUND_STATUS_CONFLICT",
                )
            payment = await self.payments.get_by_id(refund.payment_id)
            if payment is None:
                raise ResourceNotFoundException(
                    message="Payment not found",
                    code="PAYMENT_NOT_FOUND",
                )
            order = await self.orders.get_by_id(
                payment.order_id,
                for_update=True,
            )
            if order is None:
                raise ResourceNotFoundException(
                    message="Order not found",
                    code="ORDER_NOT_FOUND",
                )
            payment = await self.payments.get_by_id_for_update(payment.id)
            if payment is None:
                raise ResourceNotFoundException(
                    message="Payment not found",
                    code="PAYMENT_NOT_FOUND",
                )
            refund = await self.refunds.get_by_no(
                refund_no,
                for_update=True,
            )
            if refund is None:
                raise ResourceNotFoundException(
                    message="Refund not found",
                    code="REFUND_NOT_FOUND",
                )
            if refund.channel != "MOCK":
                refund.status = "PROCESSING"
                await self.refunds.save(refund)
                return refund
            await self.settle_locked(
                refund=refund,
                order=order,
                payment=payment,
                restock=False,
            )
        return await self._detail(refund.refund_no)
