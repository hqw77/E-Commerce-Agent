import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

ORDER_PREFIX = "ORD"
PAYMENT_PREFIX = "PAY"
AFTER_SALES_PREFIX = "AS"
REFUND_PREFIX = "RFD"


def utc_now() -> datetime:
    """Return naive UTC, matching MySQL DATETIME(6) storage."""
    return datetime.now(UTC).replace(tzinfo=None)


def utc_after(*, minutes: int = 0, hours: int = 0) -> datetime:
    return utc_now() + timedelta(minutes=minutes, hours=hours)


def new_business_no(prefix: str) -> str:
    stamp = utc_now().strftime("%Y%m%d%H%M%S")
    suffix = secrets.token_hex(4).upper()
    return f"{prefix}{stamp}{suffix}"


def new_order_no() -> str:
    return new_business_no(ORDER_PREFIX)


def new_payment_no() -> str:
    return new_business_no(PAYMENT_PREFIX)


def new_after_sales_no() -> str:
    return new_business_no(AFTER_SALES_PREFIX)


def new_refund_no() -> str:
    return new_business_no(REFUND_PREFIX)


def request_fingerprint(
    *,
    items: list[dict[str, Any]],
    receiver_name: str,
    receiver_phone: str,
    receiver_address: str,
    customer_remark: str | None,
) -> str:
    """Stable SHA-256 over the order request fields used for idempotency."""
    canonical = json.dumps(
        {
            "items": sorted(
                (
                    {
                        "sku_code": str(item["sku_code"]),
                        "quantity": int(item["quantity"]),
                    }
                    for item in items
                ),
                key=lambda item: item["sku_code"],
            ),
            "receiver_name": receiver_name,
            "receiver_phone": receiver_phone,
            "receiver_address": receiver_address,
            "customer_remark": customer_remark or "",
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def money(value: Decimal | int | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def new_idempotency_key(prefix: str = "auto") -> str:
    return f"{prefix}-{uuid4().hex}"
