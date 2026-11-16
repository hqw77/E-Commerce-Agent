"""TASK-015 local payment security checks.

No real Alipay sandbox call is made here. Real sandbox items are SKIPPED until
sandbox credentials and a public HTTPS notify URL are configured.
"""

from __future__ import annotations

from app.core.config import settings
from app.services.alipay import AlipayClient
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr


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


def test_invalid_signature_and_identity_are_rejected(monkeypatch) -> None:
    private, public = _keypair()
    monkeypatch.setattr(settings, "alipay_app_id", "sandbox-app")
    monkeypatch.setattr(settings, "alipay_seller_id", "sandbox-seller")
    monkeypatch.setattr(settings, "alipay_private_key", SecretStr(private))
    monkeypatch.setattr(settings, "alipay_public_key", SecretStr(public))
    client = AlipayClient()

    params = {
        "app_id": "sandbox-app",
        "seller_id": "sandbox-seller",
        "out_trade_no": "PAY-SEC-1",
        "total_amount": "19.90",
        "trade_status": "TRADE_SUCCESS",
        "sign_type": "RSA2",
    }
    params["sign"] = client.sign(params)
    assert client.verify_notify(params)
    assert client.validate_notify_identity(params)

    params["total_amount"] = "0.01"
    assert not client.verify_notify(params)
    # validate_notify_identity checks app_id/seller_id; amount is protected by
    # the signature and PaymentService's amount verification.
    assert client.validate_notify_identity(params)

    params["sign"] = "not-a-signature"
    assert not client.verify_notify(params)

    params["app_id"] = "another-app"
    assert not client.validate_notify_identity(params)


def test_missing_sandbox_configuration_is_explicit(monkeypatch) -> None:
    monkeypatch.setattr(settings, "alipay_app_id", "")
    monkeypatch.setattr(settings, "alipay_private_key", SecretStr(""))
    monkeypatch.setattr(settings, "alipay_public_key", SecretStr(""))
    client = AlipayClient()
    assert client.configured is False

    # This is a local configuration test, not a sandbox result.
    try:
        client.build_page_pay_url(
            out_trade_no="PAY-SEC-2",
            amount="19.90",
            subject="test",
        )
    except Exception as exc:  # noqa: BLE001 - assertion is on explicit failure
        assert "not configured" in str(exc).lower()
    else:
        raise AssertionError("unconfigured Alipay client must not build a pay URL")
