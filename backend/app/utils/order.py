"""订单/售后通用工具.

文件职责:
- 生成业务单号.
- 计算请求幂等指纹.
- 统一金额精度和 UTC 时间.

核心边界:
这里只做纯函数, 不访问数据库, 不包含业务状态判断.
"""

import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

# 业务单号前缀.
ORDER_PREFIX = "ORD"
AFTER_SALES_PREFIX = "AS"


def utc_now() -> datetime:
    """返回与 MySQL DATETIME(6) 一致的 naive UTC 时间."""
    return datetime.now(UTC).replace(tzinfo=None)


def utc_after(*, minutes: int = 0, hours: int = 0) -> datetime:
    """返回当前 UTC 时间之后的指定时长."""
    return utc_now() + timedelta(minutes=minutes, hours=hours)


def new_business_no(prefix: str) -> str:
    """生成 prefix + 时间戳 + 随机后缀的业务单号."""
    stamp = utc_now().strftime("%Y%m%d%H%M%S")
    suffix = secrets.token_hex(4).upper()
    return f"{prefix}{stamp}{suffix}"


def new_order_no() -> str:
    """生成订单号."""
    return new_business_no(ORDER_PREFIX)


def new_after_sales_no() -> str:
    """生成售后号."""
    return new_business_no(AFTER_SALES_PREFIX)


def request_fingerprint(
    *,
    items: list[dict[str, Any]],
    receiver_name: str,
    receiver_phone: str,
    receiver_address: str,
    customer_remark: str | None,
) -> str:
    """对下单参数做稳定 SHA-256, 用于幂等键冲突检测.

    items 先按 sku_code 排序, 保证同一组商品不同顺序得到相同指纹.
    """
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
    """统一金额为两位小数."""
    return Decimal(str(value)).quantize(Decimal("0.01"))


def new_idempotency_key(prefix: str = "auto") -> str:
    """生成测试或后台任务使用的幂等键."""
    return f"{prefix}-{uuid4().hex}"
