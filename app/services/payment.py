from decimal import Decimal, InvalidOperation

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AppException,
    ConflictException,
    ResourceNotFoundException,
)
from app.models.order import Order
from app.models.payment import Payment
from app.repositories.order import OrderRepository
from app.repositories.order_item import OrderItemRepository
from app.repositories.payment import PaymentRepository
from app.schemas.payment import PaymentCreateRequest
from app.services.inventory import InventoryService
from app.services.transaction import transaction_context
from app.utils.order import (
    new_payment_no,
    utc_now,
)


class PaymentService:
    """Payment creation and MOCK payment state transitions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.orders = OrderRepository(session)
        self.items = OrderItemRepository(session)
        self.payments = PaymentRepository(session)
        self.inventory = InventoryService(session)

    async def _payment_for_user(
        self,
        *,
        user_id: int,
        payment_no: str,
        for_update: bool = False,
    ) -> tuple[Payment, Order]:
        payment = await self.payments.get_by_no(payment_no)
        if payment is None or payment.user_id != user_id:
            raise ResourceNotFoundException(
                message="Payment not found",
                code="PAYMENT_NOT_FOUND",
            )
        order = await self.orders.get_by_id(
            payment.order_id,
            for_update=for_update,
        )
        if order is None:
            raise ResourceNotFoundException(
                message="Order not found",
                code="ORDER_NOT_FOUND",
            )
        if for_update:
            payment = await self.payments.get_by_no(
                payment_no,
                for_update=True,
            )
            if payment is None:
                raise ResourceNotFoundException(
                    message="Payment not found",
                    code="PAYMENT_NOT_FOUND",
                )
        return payment, order

    async def create_payment(
        self,
        *,
        user_id: int,
        order_no: str,
        request: PaymentCreateRequest,
    ) -> tuple[Payment, str | None]:
        async with transaction_context(self.session):
            order = await self.orders.get_by_no(order_no, for_update=True)
            if order is None or order.user_id != user_id:
                raise ResourceNotFoundException(
                    message="Order not found",
                    code="ORDER_NOT_FOUND",
                )
            if order.status != "PENDING_PAYMENT":
                raise ConflictException(
                    message="Order is not pending payment",
                    code="ORDER_STATUS_CONFLICT",
                )
            if order.expires_at <= utc_now():
                raise ConflictException(
                    message="Order payment window has expired",
                    code="ORDER_EXPIRED",
                )

            existing = await self.payments.get_by_order(
                order.id,
                for_update=True,
            )
            if existing is not None:
                if existing.status in {"FAILED", "CLOSED"}:
                    raise ConflictException(
                        message="Payment cannot be recreated",
                        code="PAYMENT_NOT_RETRYABLE",
                    )
                if existing.channel != request.channel:
                    raise ConflictException(
                        message="Payment channel does not match existing payment",
                        code="PAYMENT_CHANNEL_CONFLICT",
                    )
                pay_url = self._pay_url(existing)
                return existing, pay_url

            if request.channel == "ALIPAY":
                from app.services.alipay import AlipayClient

                if not AlipayClient().configured:
                    raise AppException(
                        message="Alipay sandbox is not configured",
                        code="ALIPAY_NOT_CONFIGURED",
                        status_code=503,
                    )

            payment = Payment(
                payment_no=new_payment_no(),
                order_id=order.id,
                user_id=user_id,
                channel=request.channel,
                amount=order.total_amount,
                status="PENDING",
                refunded_amount=Decimal("0.00"),
            )
            await self.payments.create(payment)
            pay_url = self._pay_url(payment)
            return payment, pay_url

    @staticmethod
    def _pay_url(payment: Payment) -> str | None:
        if payment.channel != "ALIPAY":
            return None
        from app.services.alipay import AlipayClient

        client = AlipayClient()
        if not client.configured:
            return None
        return client.build_page_pay_url(
            out_trade_no=payment.payment_no,
            amount=payment.amount,
            subject=f"Order {payment.order_id}",
        )

    async def get_payment(
        self,
        *,
        user_id: int,
        payment_no: str,
    ) -> Payment:
        payment, _ = await self._payment_for_user(
            user_id=user_id,
            payment_no=payment_no,
        )
        return payment

    async def list_payments(
        self,
        *,
        user_id: int,
        page: int,
        page_size: int,
    ) -> tuple[list[Payment], int]:
        items = await self.payments.list_for_user(
            user_id,
            page=page,
            page_size=page_size,
        )
        total = await self.payments.count_for_user(user_id)
        return items, total

    async def mock_success(
        self,
        *,
        user_id: int,
        payment_no: str,
        provider_trade_no: str | None = None,
    ) -> tuple[Payment, bool]:
        async with transaction_context(self.session):
            payment, order = await self._payment_for_user(
                user_id=user_id,
                payment_no=payment_no,
                for_update=True,
            )
            if payment.channel != "MOCK":
                raise ConflictException(
                    message="MOCK payment is not available for this channel",
                    code="PAYMENT_CHANNEL_CONFLICT",
                )
            late = await self._apply_success(
                payment=payment,
                order=order,
                provider_trade_no=provider_trade_no,
            )
            await self.payments.save(payment)
            await self.orders.save(order)
        return payment, late

    async def mock_fail(
        self,
        *,
        user_id: int,
        payment_no: str,
    ) -> Payment:
        async with transaction_context(self.session):
            payment, _ = await self._payment_for_user(
                user_id=user_id,
                payment_no=payment_no,
                for_update=True,
            )
            if payment.channel != "MOCK":
                raise ConflictException(
                    message="MOCK payment is not available for this channel",
                    code="PAYMENT_CHANNEL_CONFLICT",
                )
            if payment.status in {"SUCCESS", "PARTIALLY_REFUNDED", "REFUNDED"}:
                raise ConflictException(
                    message="Successful payment cannot be failed",
                    code="PAYMENT_STATUS_CONFLICT",
                )
            if payment.status == "PENDING":
                payment.status = "FAILED"
                payment.failure_code = "MOCK_FAILED"
                payment.failure_message = "Mock payment failed"
                await self.payments.save(payment)
        return payment

    async def _apply_success(
        self,
        *,
        payment: Payment,
        order: Order,
        provider_trade_no: str | None,
    ) -> bool:
        if payment.status in {
            "SUCCESS",
            "PARTIALLY_REFUNDED",
            "REFUNDED",
        }:
            return payment.exception_reason == "LATE_PAYMENT"

        paid_at = utc_now()
        payment.status = "SUCCESS"
        payment.paid_at = paid_at
        if provider_trade_no:
            payment.provider_trade_no = provider_trade_no

        items = await self.items.list_by_order(order.id)

        if order.status in {"CANCELLED", "CLOSED"}:
            payment.exception_reason = "LATE_PAYMENT"
            order.payment_status = "PAID"
            order.paid_amount = payment.amount
            order.paid_at = paid_at
            return True

        if order.status == "PENDING_PAYMENT" and order.expires_at <= paid_at:
            for item in sorted(items, key=lambda value: value.sku_id):
                await self.inventory.release(
                    sku_id=item.sku_id,
                    quantity=item.quantity,
                    idempotency_key=(f"order:{order.id}:line:{item.id}:release"),
                    business_type="ORDER",
                    business_id=order.id,
                    business_item_id=item.id,
                )
            payment.exception_reason = "LATE_PAYMENT"
            order.status = "CLOSED"
            order.closed_at = paid_at
            order.payment_status = "PAID"
            order.paid_amount = payment.amount
            order.paid_at = paid_at
            return True

        if order.status != "PENDING_PAYMENT":
            raise ConflictException(
                message="Order cannot accept payment in its current state",
                code="ORDER_STATUS_CONFLICT",
            )

        for item in sorted(items, key=lambda value: value.sku_id):
            await self.inventory.deduct_reserved(
                sku_id=item.sku_id,
                quantity=item.quantity,
                idempotency_key=f"order:{order.id}:line:{item.id}:ship",
                business_type="ORDER",
                business_id=order.id,
                business_item_id=item.id,
            )
        order.status = "PAID"
        order.payment_status = "PAID"
        order.paid_amount = payment.amount
        order.paid_at = paid_at
        return False

    async def handle_alipay_success(
        self,
        *,
        payment_no: str,
        amount: Decimal,
        provider_trade_no: str | None,
    ) -> bool:
        """Apply a verified Alipay success notification."""
        async with transaction_context(self.session):
            payment = await self.payments.get_by_no(payment_no)
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
                payment_no,
                for_update=True,
            )
            if payment is None:
                raise ResourceNotFoundException(
                    message="Payment not found",
                    code="PAYMENT_NOT_FOUND",
                )
            if payment.amount != amount:
                raise ConflictException(
                    message="Payment amount mismatch",
                    code="PAYMENT_AMOUNT_MISMATCH",
                )
            if payment.channel != "ALIPAY":
                raise ConflictException(
                    message="Payment channel mismatch",
                    code="PAYMENT_CHANNEL_CONFLICT",
                )
            late = await self._apply_success(
                payment=payment,
                order=order,
                provider_trade_no=provider_trade_no,
            )
            await self.payments.save(payment)
            await self.orders.save(order)
        return late

    async def sync_payment(self, *, payment_no: str) -> Payment:
        """Query Alipay outside a transaction and apply a trusted result."""
        payment = await self.payments.get_by_no(payment_no)
        if payment is None:
            raise ResourceNotFoundException(
                message="Payment not found",
                code="PAYMENT_NOT_FOUND",
            )
        if payment.channel != "ALIPAY":
            return payment

        from app.services.alipay import AlipayClient

        client = AlipayClient()
        if not client.configured:
            return payment
        result = await client.query_trade(out_trade_no=payment.payment_no)
        response = result.get("alipay_trade_query_response", {})
        if response.get("code") != "10000":
            return payment
        if response.get("trade_status") not in {
            "TRADE_SUCCESS",
            "TRADE_FINISHED",
        }:
            return payment
        try:
            amount = Decimal(str(response.get("total_amount", "")))
        except (InvalidOperation, TypeError, ValueError):
            return payment
        await self.handle_alipay_success(
            payment_no=payment.payment_no,
            amount=amount,
            provider_trade_no=response.get("trade_no"),
        )
        refreshed = await self.payments.get_by_no(payment.payment_no)
        if refreshed is None:
            raise ResourceNotFoundException(
                message="Payment not found",
                code="PAYMENT_NOT_FOUND",
            )
        return refreshed
