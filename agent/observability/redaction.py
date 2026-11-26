"""Agent Trace 数据脱敏.

文件职责:
- 对 Trace 中的参数和结果做递归脱敏.
- 屏蔽密码, Token, 私钥, 手机号, 地址等敏感字段.
- 限制文本长度和集合元素数量, 防止日志膨胀.

核心边界:
Trace 是诊断数据, 不是业务数据; 不能因为 Tool 返回了就原样落日志.
"""

from __future__ import annotations

import re
from typing import Any

# 统一脱敏占位符.
REDACTED = "[REDACTED]"
# 单个字符串最多保留长度.
MAX_TEXT_LENGTH = 200
# 单个字典/列表最多保留元素数.
MAX_COLLECTION_ITEMS = 20

# 命中这些 key 的字段整体替换为 REDACTED.
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

# 即使 key 名称正常, value 命中这些模式也会被脱敏.
_SECRET_VALUE_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(
        r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
    ),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{10,}", re.IGNORECASE),
)


def _is_sensitive_key(key: str) -> bool:
    """判断字段名是否包含敏感标记."""
    lowered = key.casefold()
    return any(marker in lowered for marker in _SENSITIVE_KEY_MARKERS)


def _redact_text(value: str) -> str:
    """对字符串做密钥检测和长度截断."""
    if any(pattern.search(value) for pattern in _SECRET_VALUE_PATTERNS):
        return REDACTED
    if len(value) > MAX_TEXT_LENGTH:
        return value[:MAX_TEXT_LENGTH] + "...[truncated]"
    return value


def redact_payload(value: Any) -> Any:
    """递归返回脱敏, 限长且可 JSON 序列化的副本."""
    # ① 字典按 key 脱敏, 并限制条目数.
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
    # ② 列表/元组递归处理, 超出上限追加截断标记.
    if isinstance(value, (list, tuple)):
        items = [redact_payload(item) for item in value[:MAX_COLLECTION_ITEMS]]
        if len(value) > MAX_COLLECTION_ITEMS:
            items.append("... [truncated]")
        return items
    # ③ 标量保留, 其他对象转字符串后脱敏.
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _redact_text(str(value))
