import json

from fastapi import Request

from app.core.exceptions import ValidationException


async def reject_duplicate_json_keys(request: Request) -> None:
    """Reject raw JSON objects that contain duplicate keys."""
    body = await request.body()

    if not body:
        return

    def object_pairs_hook(pairs: list[tuple[str, object]]) -> dict:
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
        # FastAPI/Pydantic will produce the standard validation error.
        return
