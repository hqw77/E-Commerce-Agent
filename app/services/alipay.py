import base64
import json
from binascii import Error as BinasciiError
from datetime import datetime
from decimal import Decimal
from typing import Any, cast
from urllib.parse import urlencode

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.core.config import settings


class AlipayConfigurationError(RuntimeError):
    """Raised when Alipay sandbox configuration is incomplete."""


class AlipayClient:
    """Small RSA2 adapter for the Alipay sandbox.

    The adapter intentionally keeps the boundary narrow: request construction
    and notification verification. Network calls are performed by callers or
    a later scheduled reconciliation task.
    """

    def __init__(self) -> None:
        self.app_id = settings.alipay_app_id
        self.seller_id = settings.alipay_seller_id
        self.gateway = settings.alipay_gateway
        self.notify_url = settings.alipay_notify_url
        self.return_url = settings.alipay_return_url
        self._private_key = settings.alipay_private_key.get_secret_value()
        self._public_key = settings.alipay_public_key.get_secret_value()

    @property
    def configured(self) -> bool:
        return bool(self.app_id and self._private_key and self._public_key)

    @staticmethod
    def _canonical(params: dict[str, Any]) -> str:
        return "&".join(
            f"{key}={params[key]}"
            for key in sorted(params)
            if params[key] not in (None, "")
        )

    def sign(self, params: dict[str, Any]) -> str:
        if not self._private_key:
            raise AlipayConfigurationError("Alipay private key is not configured")
        key = cast(
            rsa.RSAPrivateKey,
            serialization.load_pem_private_key(
                self._private_key.encode("utf-8"),
                password=None,
            ),
        )
        unsigned = {
            key: value
            for key, value in params.items()
            if key not in {"sign", "sign_type"}
        }
        signature = key.sign(
            self._canonical(unsigned).encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("ascii")

    def build_page_pay_url(
        self,
        *,
        out_trade_no: str,
        amount: Decimal,
        subject: str,
    ) -> str:
        if not self.configured:
            raise AlipayConfigurationError("Alipay sandbox is not configured")

        biz_content = json.dumps(
            {
                "out_trade_no": out_trade_no,
                "total_amount": str(amount),
                "subject": subject,
                "product_code": "FAST_INSTANT_TRADE_PAY",
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        params: dict[str, Any] = {
            "app_id": self.app_id,
            "method": "alipay.trade.page.pay",
            "format": "JSON",
            "charset": "utf-8",
            "sign_type": "RSA2",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0",
            "notify_url": self.notify_url or None,
            "return_url": self.return_url or None,
            "biz_content": biz_content,
        }
        params = {key: value for key, value in params.items() if value}
        params["sign"] = self.sign(params)
        return f"{self.gateway}?{urlencode(params)}"

    def verify_notify(self, params: dict[str, Any]) -> bool:
        if not self._public_key:
            return False
        signature = str(params.get("sign", ""))
        if not signature:
            return False
        unsigned = {
            key: value
            for key, value in params.items()
            if key not in {"sign", "sign_type"}
        }
        try:
            key = cast(
                rsa.RSAPublicKey,
                serialization.load_pem_public_key(self._public_key.encode("utf-8")),
            )
            key.verify(
                base64.b64decode(signature),
                self._canonical(unsigned).encode("utf-8"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            return True
        except (ValueError, TypeError, InvalidSignature, BinasciiError):
            return False

    def validate_notify_identity(self, params: dict[str, Any]) -> bool:
        if str(params.get("app_id", "")) != self.app_id:
            return False
        seller_id = self.seller_id
        return not (seller_id and str(params.get("seller_id", "")) != seller_id)

    def _request_params(
        self,
        *,
        method: str,
        biz_content: dict[str, Any],
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "app_id": self.app_id,
            "method": method,
            "format": "JSON",
            "charset": "utf-8",
            "sign_type": "RSA2",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0",
            "biz_content": json.dumps(
                biz_content,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        }
        params["sign"] = self.sign(params)
        return params

    async def query_trade(self, *, out_trade_no: str) -> dict[str, Any]:
        if not self.configured:
            raise AlipayConfigurationError("Alipay sandbox is not configured")
        params = self._request_params(
            method="alipay.trade.query",
            biz_content={"out_trade_no": out_trade_no},
        )
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(self.gateway, data=params)
            response.raise_for_status()
            return response.json()

    async def close_trade(self, *, out_trade_no: str) -> dict[str, Any]:
        if not self.configured:
            raise AlipayConfigurationError("Alipay sandbox is not configured")
        params = self._request_params(
            method="alipay.trade.close",
            biz_content={"out_trade_no": out_trade_no},
        )
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(self.gateway, data=params)
            response.raise_for_status()
            return response.json()
