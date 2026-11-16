from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AppException,
    ConflictException,
    ResourceNotFoundException,
)
from app.models.after_sale import AfterSale
from app.models.order import Order
from app.models.payment import Payment
from app.models.refund import Refund
from app.repositories.after_sale import AfterSaleRepository
from app.repositories.order import OrderRepository
from app.repositories.order_item import OrderItemRepository
from app.repositories.payment import PaymentRepository
from app.repositories.refund import RefundRepository
from app.schemas.payment import ManualRefundRequest
from app.services.alipay import AlipayClient, AlipayConfigurationError
from app.services.inventory import InventoryService
from app.services.transaction import transaction_context
from app.utils.order import new_refund_no, utc_now


@dataclass
class LockedRefund:
    refund: Refund
    order: Order
    payment: Payment
    after_sale: AfterSale | None


class RefundService:
    """Refund amount validation and refund state transitions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.orders = OrderRepository(session)
        self.items = OrderItemRepository(session)
        self.payments = PaymentRepository(session)
        self.refunds = RefundRepository(session)
        self.after_sales = AfterSaleRepository(session)
        self.inventory = InventoryService(session)

    async def _detail(self, refund_no: str) -> Refund:
        refund = await self.refunds.get_by_no(refund_no)
        if refund is None:
            raise ResourceNotFoundException(
                message="Refund not found",
                code="REFUND_NOT_FOUND",
            )
        return refund

    async def _lock_refund(self, refund_no: str) -> LockedRefund:
        """Lock order -> items -> payment -> after-sale -> refund."""
        refund = await self.refunds.get_by_no(refund_no)
        if refund is None:
            raise ResourceNotFoundException(
                message="Refund not found",
                code="REFUND_NOT_FOUND",
            )
        order = await self.orders.get_by_id(
            refund.order_id,
            for_update=True,
        )
        if order is None:
            raise ResourceNotFoundException(
                message="Order not found",
                code="ORDER_NOT_FOUND",
            )
        order_items = await self.items.list_by_order(order.id)
        for item in sorted(order_items, key=lambda value: value.sku_id):
            await self.items.get_by_id(item.id, for_update=True)

        payment = await self.payments.get_by_id_for_update(refund.payment_id)
        if payment is None:
            raise ResourceNotFoundException(
                message="Payment not found",
                code="PAYMENT_NOT_FOUND",
            )

        after_sale = None
        if refund.after_sales_id is not None:
            after_sale = await self.after_sales.get_by_id_for_update(
                refund.after_sales_id
            )

        locked_refund = await self.refunds.get_by_no(
            refund_no,
            for_update=True,
        )
        if locked_refund is None:
            raise ResourceNotFoundException(
                message="Refund not found",
                code="REFUND_NOT_FOUND",
            )
        return LockedRefund(
            refund=locked_refund,
            order=order,
            payment=payment,
            after_sale=after_sale,
        )

    async def _claim_alipay(self, refund_no: str) -> tuple[bool, Refund]:
        async with transaction_context(self.session):
            locked = await self._lock_refund(refund_no)
            if locked.refund.channel != "ALIPAY":
                return False, locked.refund
            if locked.refund.status == "SUCCESS":
                return False, locked.refund
            if locked.refund.status == "PROCESSING":
                return False, locked.refund
            if locked.refund.status not in {"PENDING", "FAILED"}:
                raise ConflictException(
                    message="Refund cannot be sent in its current state",
                    code="REFUND_STATUS_CONFLICT",
                )
            locked.refund.status = "PROCESSING"
            locked.refund.failure_code = None
            locked.refund.failure_message = None
            await self.refunds.save(locked.refund)
        return True, locked.refund

    async def _finalize_alipay_success(
        self,
        *,
        refund_no: str,
        provider_refund_no: str | None,
    ) -> Refund:
        async with transaction_context(self.session):
            locked = await self._lock_refund(refund_no)
            if locked.refund.status == "SUCCESS":
                return locked.refund
            if provider_refund_no:
                locked.refund.provider_refund_no = provider_refund_no
            await self.settle_locked(
                refund=locked.refund,
                order=locked.order,
                payment=locked.payment,
                after_sale=locked.after_sale,
                restock=True,
            )
        return await self._detail(refund_no)

    async def _mark_alipay_failed(
        self,
        *,
        refund_no: str,
        failure_code: str,
        failure_message: str,
    ) -> Refund:
        async with transaction_context(self.session):
            locked = await self._lock_refund(refund_no)
            if locked.refund.status == "SUCCESS":
                return locked.refund
            locked.refund.status = "FAILED"
            locked.refund.failure_code = failure_code[:64]
            locked.refund.failure_message = failure_message[:255]
            if (
                locked.after_sale is not None
                and locked.after_sale.status == "REFUNDING"
            ):
                locked.after_sale.status = "REFUND_FAILED"
                await self.after_sales.save(locked.after_sale)
            await self.refunds.save(locked.refund)
        return await self._detail(refund_no)

    @staticmethod
    def _decimal(value: object) -> Decimal | None:
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None

    async def _handle_refund_response(
        self,
        *,
        refund: Refund,
        payment: Payment,
        result: dict[str, object],
    ) -> Refund:
        body = result.get("alipay_trade_refund_response")
        if not isinstance(body, dict):
            # A malformed response is an unknown result: query later.
            return await self._detail(refund.refund_no)

        code = str(body.get("code", ""))
        if code != "10000":
            return await self._mark_alipay_failed(
                refund_no=refund.refund_no,
                failure_code=code or "ALIPAY_REFUND_ERROR",
                failure_message=str(body.get("sub_msg") or body.get("msg") or ""),
            )

        if body.get("fund_change") != "Y":
            # Alipay accepted the request but did not confirm a fund change.
            # Keep PROCESSING and require a refund query.
            return await self._detail(refund.refund_no)

        if body.get("out_trade_no") not in (None, payment.payment_no):
            return await self._mark_alipay_failed(
                refund_no=refund.refund_no,
                failure_code="ALIPAY_OUT_TRADE_NO_MISMATCH",
                failure_message="Refund response out_trade_no mismatch",
            )
        if body.get("out_request_no") not in (None, refund.refund_no):
            return await self._mark_alipay_failed(
                refund_no=refund.refund_no,
                failure_code="ALIPAY_OUT_REQUEST_NO_MISMATCH",
                failure_message="Refund response out_request_no mismatch",
            )
        refund_fee = self._decimal(body.get("refund_fee"))
        if refund_fee is not None and refund_fee != refund.amount:
            return await self._mark_alipay_failed(
                refund_no=refund.refund_no,
                failure_code="ALIPAY_REFUND_AMOUNT_MISMATCH",
                failure_message="Refund response amount mismatch",
            )

        return await self._finalize_alipay_success(
            refund_no=refund.refund_no,
            provider_refund_no=str(body.get("trade_no") or ""),
        )

    async def _handle_refund_query_response(
        self,
        *,
        refund: Refund,
        payment: Payment,
        result: dict[str, object],
    ) -> Refund:
        body = result.get("alipay_trade_fastpay_refund_query_response")
        if not isinstance(body, dict):
            return await self._detail(refund.refund_no)
        if str(body.get("code", "")) != "10000":
            return await self._detail(refund.refund_no)
        refund_status = body.get("refund_status")
        if refund_status != "REFUND_SUCCESS" and body.get("fund_change") != "Y":
            return await self._detail(refund.refund_no)
        if body.get("out_trade_no") not in (None, payment.payment_no):
            return await self._detail(refund.refund_no)
        if body.get("out_request_no") not in (None, refund.refund_no):
            return await self._detail(refund.refund_no)
        refund_amount = self._decimal(
            body.get("refund_amount") or body.get("refund_fee")
        )
        if refund_amount is not None and refund_amount != refund.amount:
            return await self._detail(refund.refund_no)
        return await self._finalize_alipay_success(
            refund_no=refund.refund_no,
            provider_refund_no=str(body.get("trade_no") or ""),
        )

    async def process_alipay_refund(self, *, refund_no: str) -> Refund:
        """Send a sandbox refund outside any database transaction."""
        refund = await self._detail(refund_no)
        if refund.channel != "ALIPAY":
            return refund
        if refund.status == "SUCCESS":
            return refund

        client = AlipayClient()
        if not client.configured:
            raise AppException(
                message="Alipay sandbox is not configured",
                code="ALIPAY_NOT_CONFIGURED",
                status_code=503,
            )

        claimed, claimed_refund = await self._claim_alipay(refund_no)
        if not claimed:
            # A concurrent request already owns PROCESSING; query instead of
            # sending the refund a second time.
            return await self.sync_alipay_refund(refund_no=refund_no)

        payment = await self.payments.get_by_id(claimed_refund.payment_id)
        if payment is None:
            raise ResourceNotFoundException(
                message="Payment not found",
                code="PAYMENT_NOT_FOUND",
            )

        try:
            result = await client.refund_trade(
                out_trade_no=payment.payment_no,
                refund_amount=claimed_refund.amount,
                out_request_no=claimed_refund.refund_no,
                refund_reason=claimed_refund.reason,
            )
        except (httpx.HTTPError, AlipayConfigurationError, ValueError):
            # The request may have reached Alipay: keep PROCESSING and query.
            return await self._detail(refund_no)

        return await self._handle_refund_response(
            refund=claimed_refund,
            payment=payment,
            result=result,
        )

    async def sync_alipay_refund(self, *, refund_no: str) -> Refund:
        """Query an unknown Alipay refund result; never create a new refund."""
        async with transaction_context(self.session):
            refund = await self._detail(refund_no)
            if refund.channel != "ALIPAY" or refund.status == "SUCCESS":
                return refund
            payment = await self.payments.get_by_id(refund.payment_id)
            if payment is None:
                raise ResourceNotFoundException(
                    message="Payment not found",
                    code="PAYMENT_NOT_FOUND",
                )
            payment_no = payment.payment_no

        client = AlipayClient()
        if not client.configured:
            raise AppException(
                message="Alipay sandbox is not configured",
                code="ALIPAY_NOT_CONFIGURED",
                status_code=503,
            )
        try:
            result = await client.query_refund(
                out_trade_no=payment_no,
                out_request_no=refund.refund_no,
            )
        except (httpx.HTTPError, AlipayConfigurationError, ValueError):
            return await self._detail(refund_no)
        return await self._handle_refund_query_response(
            refund=refund,
            payment=payment,
            result=result,
        )

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
        if payment.channel == "ALIPAY" and amount != payment.amount:
            raise ConflictException(
                message="Alipay sandbox supports full refunds only",
                code="REFUND_NOT_ALLOWED",
            )
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

        if refund.channel == "ALIPAY" and refund.status != "SUCCESS":
            return await self.process_alipay_refund(refund_no=refund.refund_no)
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
        refund = await self._detail(refund_no)
        if refund.status not in {"FAILED", "PENDING"}:
            raise ConflictException(
                message="Only failed or pending refunds can be retried",
                code="REFUND_STATUS_CONFLICT",
            )
        if refund.channel == "ALIPAY":
            return await self.process_alipay_refund(refund_no=refund_no)

        async with transaction_context(self.session):
            order = await self.orders.get_by_id(
                refund.order_id,
                for_update=True,
            )
            if order is None:
                raise ResourceNotFoundException(
                    message="Order not found",
                    code="ORDER_NOT_FOUND",
                )
            payment = await self.payments.get_by_id_for_update(refund.payment_id)
            if payment is None:
                raise ResourceNotFoundException(
                    message="Payment not found",
                    code="PAYMENT_NOT_FOUND",
                )
            locked_refund = await self.refunds.get_by_no(
                refund_no,
                for_update=True,
            )
            if locked_refund is None:
                raise ResourceNotFoundException(
                    message="Refund not found",
                    code="REFUND_NOT_FOUND",
                )
            await self.settle_locked(
                refund=locked_refund,
                order=order,
                payment=payment,
                restock=False,
            )
        return await self._detail(refund_no)
