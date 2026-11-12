from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from app.core.config import Settings
from app.db.session import AsyncSessionLocal
from app.services.auth import AuthService


@pytest.mark.asyncio
async def test_logout_after_autobegin_does_not_raise() -> None:
    """Reproduce the original SQLAlchemy autobegin conflict.

    The authentication dependency loads the current user before the
    logout endpoint runs, so the request session is already inside an
    implicit transaction when AuthService.logout is called.
    """
    config = Settings(
        _env_file=None,
        app_env="testing",
        jwt_secret_key="a" * 32,
    )

    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT 1"))
        assert session.in_transaction() is True

        service = AuthService(session, config)
        current = SimpleNamespace(
            id=1,
            user_id=1,
            family_id="family-autobegin",
        )

        service.refresh_repository.get_by_token_hash_for_update = (
            AsyncMock(return_value=current)
        )
        service.refresh_repository.revoke_family = AsyncMock()

        await service.logout(user_id=1, refresh_token="refresh-token")

        assert session.in_transaction() is False
        service.refresh_repository.revoke_family.assert_awaited_once()
