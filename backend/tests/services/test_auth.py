from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.core.config import Settings
from app.core.exceptions import AuthenticationException
from app.services.auth import AuthService
from sqlalchemy.ext.asyncio import AsyncSession


def make_user(
    user_id: int = 1,
    email: str = "alice@example.com",
    password_hash: str = "hashed-password",
    is_active: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        email=email,
        password_hash=password_hash,
        is_active=is_active,
    )


@pytest.fixture
def config() -> Settings:
    return Settings(
        _env_file=None,
        app_env="testing",
        jwt_secret_key="a" * 32,
    )


@pytest.fixture
def session() -> MagicMock:
    mocked_session = MagicMock(spec=AsyncSession)

    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock(return_value=None)
    transaction.__aexit__ = AsyncMock(return_value=False)

    mocked_session.begin.return_value = transaction
    mocked_session.commit = AsyncMock()

    return mocked_session


@pytest.fixture
def service(session: MagicMock, config: Settings) -> AuthService:
    return AuthService(session, config)


@pytest.mark.asyncio
async def test_login_success(
    service: AuthService,
    config: Settings,
) -> None:
    user = make_user()
    service.user_repository.get_by_email = AsyncMock(return_value=user)

    with patch("app.services.auth.verify_password", return_value=True):
        response = await service.login(
            email=" Alice@Example.com ",
            password="Password123",
        )

    assert response.access_token
    assert response.token_type == "bearer"
    assert response.expires_in == config.jwt_access_token_expire_minutes * 60
    assert not hasattr(response, "refresh_token")


@pytest.mark.asyncio
async def test_login_unknown_user_runs_dummy_verification(
    service: AuthService,
) -> None:
    service.user_repository.get_by_email = AsyncMock(return_value=None)

    with patch("app.services.auth.verify_dummy_password") as dummy, pytest.raises(
        AuthenticationException
    ):
        await service.login(
            email="missing@example.com",
            password="Password123",
        )

    dummy.assert_called_once_with("Password123")


@pytest.mark.asyncio
async def test_login_wrong_password(
    service: AuthService,
) -> None:
    user = make_user()
    service.user_repository.get_by_email = AsyncMock(return_value=user)

    with patch("app.services.auth.verify_password", return_value=False), pytest.raises(
        AuthenticationException
    ):
        await service.login(
            email="alice@example.com",
            password="WrongPassword",
        )


@pytest.mark.asyncio
async def test_login_inactive_user(
    service: AuthService,
) -> None:
    user = make_user(is_active=False)
    service.user_repository.get_by_email = AsyncMock(return_value=user)

    with patch("app.services.auth.verify_password", return_value=True), pytest.raises(
        AuthenticationException
    ):
        await service.login(
            email="alice@example.com",
            password="Password123",
        )


@pytest.mark.asyncio
async def test_get_user_by_id_rejects_inactive_user(
    service: AuthService,
) -> None:
    service.user_repository.get_by_id = AsyncMock(
        return_value=make_user(is_active=False)
    )

    with pytest.raises(AuthenticationException):
        await service.get_user_by_id(1)
