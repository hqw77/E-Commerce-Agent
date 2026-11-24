"""管理端请求的附加校验.

Python 的 json.loads 默认会保留最后一个重复 key, 这对于 SKU 属性这类
安全敏感字段可能造成歧义. 这里在 Pydantic 解析前主动拒绝重复 key.
"""

import json

from fastapi import Request

from app.core.exceptions import ValidationException


async def reject_duplicate_json_keys(request: Request) -> None:
    """拒绝包含重复 key 的原始 JSON 对象, 避免解析结果与客户端意图不一致."""
    body = await request.body()

    if not body:
        return

    def object_pairs_hook(pairs: list[tuple[str, object]]) -> dict:
        # object_pairs_hook 会收到原始 key 顺序, 因此可以检测重复项.
        keys = [key for key, _value in pairs]

        if len(keys) != len(set(keys)):
            raise ValidationException(
                message="JSON object contains duplicate keys",
                code="SKU_ATTRIBUTES_INVALID",
            )

        return dict(pairs)

    try:
        json.loads(body, object_pairs_hook=object_pairs_hook)
    except json.JSONDecodeError:
        # 非法 JSON 交给 FastAPI/Pydantic 生成标准 422, 这里不重复处理.
        return
