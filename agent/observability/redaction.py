"""Redaction helpers for Agent trace payloads.

Trace data is diagnostic, not business data. Never allow credentials or PII to
reach logs simply because a Tool or API returned them.
"""

from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"
MAX_TEXT_LENGTH = 200
MAX_COLLECTION_ITEMS = 20

_SENSITIVE_KEY_MARKERS = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "api_key",
    "apikey",
    "private_key",
    "access_token",
    "refresh_token",
    "nonce",
    "signature",
    "cookie",
    "jwt",
    "phone",
    "mobile",
    "address",
    "email",
    "id_card",
    "identity",
    "payment_key",
    "confirmation_id",
    "tracking_no",
    "receiver_name",
    "recipient",
)

_SECRET_VALUE_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(
        r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
    ),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{10,}", re.IGNORECASE),
)


def _is_sensitive_key(key: str) -> bool:
    lowered = key.casefold()
    return any(marker in lowered for marker in _SENSITIVE_KEY_MARKERS)


def _redact_text(value: str) -> str:
    if any(pattern.search(value) for pattern in _SECRET_VALUE_PATTERNS):
        return REDACTED
    if len(value) > MAX_TEXT_LENGTH:
        return value[:MAX_TEXT_LENGTH] + "...[truncated]"
    return value


def redact_payload(value: Any) -> Any:
    """Return a redacted, bounded, JSON-serializable copy of a payload."""
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= MAX_COLLECTION_ITEMS:
                result["_truncated"] = True
                break
            key_text = str(key)
            result[key_text] = (
                REDACTED if _is_sensitive_key(key_text) else redact_payload(item)
            )
        return result
    if isinstance(value, (list, tuple)):
        items = [redact_payload(item) for item in value[:MAX_COLLECTION_ITEMS]]
        if len(value) > MAX_COLLECTION_ITEMS:
            items.append("... [truncated]")
        return items
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _redact_text(str(value))
