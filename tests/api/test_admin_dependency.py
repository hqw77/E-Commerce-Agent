from types import SimpleNamespace

import pytest

from app.api.dependencies import get_current_admin
from app.core.exceptions import PermissionDeniedException


@pytest.mark.asyncio
async def test_get_current_admin_accepts_admin() -> None:
    user = SimpleNamespace(id=1, is_admin=True)

    result = await get_current_admin(user)

    assert result is user


@pytest.mark.asyncio
async def test_get_current_admin_rejects_regular_user() -> None:
    user = SimpleNamespace(id=1, is_admin=False)

    with pytest.raises(PermissionDeniedException) as exc_info:
        await get_current_admin(user)

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "PERMISSION_DENIED"
