import json
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr

from app.core.config import settings
from app.services.alipay import AlipayClient


def _keypair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return private, public


def test_alipay_build_url_and_verify_notify(monkeypatch):
    private, public = _keypair()
    monkeypatch.setattr(settings, "alipay_app_id", "sandbox-app")
    monkeypatch.setattr(settings, "alipay_seller_id", "sandbox-seller")
    monkeypatch.setattr(settings, "alipay_private_key", SecretStr(private))
    monkeypatch.setattr(settings, "alipay_public_key", SecretStr(public))
    monkeypatch.setattr(settings, "alipay_notify_url", "http://test/notify")

    client = AlipayClient()
    assert client.configured is True

    url = client.build_page_pay_url(
        out_trade_no="PAY123",
        amount="19.90",
        subject="Test order",
    )
    query = parse_qs(urlparse(url).query)
    assert query["app_id"] == ["sandbox-app"]
    assert query["method"] == ["alipay.trade.page.pay"]
    assert "sign" in query
    assert "19.90" in query["biz_content"][0]

    params = {
        "app_id": "sandbox-app",
        "seller_id": "sandbox-seller",
        "out_trade_no": "PAY123",
        "total_amount": "19.90",
        "trade_status": "TRADE_SUCCESS",
        "sign_type": "RSA2",
    }
    params["sign"] = client.sign(params)
    assert client.verify_notify(params) is True
    assert client.validate_notify_identity(params) is True

    params["total_amount"] = "20.00"
    assert client.verify_notify(params) is False


@pytest.mark.asyncio
async def test_alipay_refund_request_contains_stable_request_no(monkeypatch):
    private, public = _keypair()
    monkeypatch.setattr(settings, "alipay_app_id", "sandbox-app")
    monkeypatch.setattr(settings, "alipay_private_key", SecretStr(private))
    monkeypatch.setattr(settings, "alipay_public_key", SecretStr(public))

    captured: dict[str, str] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"alipay_trade_refund_response": {"code": "10000"}}

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, data):
            captured.update(data)
            return FakeResponse()

    monkeypatch.setattr(
        "app.services.alipay.httpx.AsyncClient",
        FakeClient,
    )
    client = AlipayClient()
    await client.refund_trade(
        out_trade_no="PAY123",
        refund_amount="19.90",
        out_request_no="RFD123",
        refund_reason="full refund",
    )

    assert captured["method"] == "alipay.trade.refund"
    assert captured["sign_type"] == "RSA2"
    assert "sign" in captured
    biz = json.loads(captured["biz_content"])
    assert biz["out_trade_no"] == "PAY123"
    assert biz["out_request_no"] == "RFD123"
    assert biz["refund_amount"] == "19.90"
