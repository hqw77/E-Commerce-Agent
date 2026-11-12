from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import (
    AuthenticationException,
    InvalidTokenException,
    TokenExpiredException,
)
from app.core.security import verify_dummy_password
from app.db.session import AsyncSessionLocal
from app.services.auth import AuthService, _hash_refresh_token


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


def make_refresh_session(
    *,
    user_id: int = 1,
    family_id: str = "family-1",
    revoked_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        user_id=user_id,
        family_id=family_id,
        revoked_at=revoked_at,
        expires_at=expires_at
        or (
            datetime.now(UTC).replace(tzinfo=None)
            + timedelta(days=1)
        ),
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


# Login


@pytest.mark.asyncio
async def test_login_success(
    service: AuthService,
    config: Settings,
) -> None:
    user = make_user()

    service.user_repository.get_by_email = AsyncMock(return_value=user)
    service.refresh_repository.create = AsyncMock(
        return_value=make_refresh_session()
    )

    with (
        patch("app.services.auth.verify_password", return_value=True),
        patch("app.services.auth.verify_dummy_password") as dummy,
    ):
        response = await service.login(
            email=" Alice@Example.com ",
            password="Password123",
        )

    assert response.token_type == "bearer"
    assert response.expires_in == config.jwt_access_token_expire_minutes * 60
    assert response.refresh_token

    claims = service.token_service.decode_access_token(
        response.access_token
    )
    assert claims.user_id == user.id

    service.user_repository.get_by_email.assert_awaited_once_with(
        "alice@example.com"
    )
    dummy.assert_not_called()


@pytest.mark.asyncio
async def test_login_unknown_user_runs_dummy_verification(
    service: AuthService,
) -> None:
    service.user_repository.get_by_email = AsyncMock(return_value=None)

    with (
        patch(
            "app.services.auth.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=False,
        ) as to_thread,
        patch("app.services.auth.verify_password") as real_verify,
        pytest.raises(AuthenticationException) as exc_info,
    ):
        await service.login(
            email="missing@example.com",
            password="Password123",
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.message == "Invalid email or password"
    assert exc_info.value.code == "AUTHENTICATION_FAILED"

    to_thread.assert_awaited_once()
    assert to_thread.await_args.args == (
        verify_dummy_password,
        "Password123",
    )
    real_verify.assert_not_called()


@pytest.mark.asyncio
async def test_login_wrong_password_does_not_use_dummy_verification(
    service: AuthService,
) -> None:
    service.user_repository.get_by_email = AsyncMock(
        return_value=make_user()
    )

    with (
        patch("app.services.auth.verify_password", return_value=False),
        patch(
            "app.services.auth.verify_dummy_password"
        ) as dummy,
        pytest.raises(AuthenticationException) as exc_info,
    ):
        await service.login(
            email="alice@example.com",
            password="WrongPassword",
        )

    assert exc_info.value.message == "Invalid email or password"
    dummy.assert_not_called()


@pytest.mark.asyncio
async def test_login_inactive_user(service: AuthService) -> None:
    service.user_repository.get_by_email = AsyncMock(
        return_value=make_user(is_active=False)
    )

    with (
        patch("app.services.auth.verify_password", return_value=True),
        pytest.raises(AuthenticationException) as exc_info,
    ):
        await service.login(
            email="alice@example.com",
            password="Password123",
        )

    assert exc_info.value.message == "Invalid email or password"


# Refresh


@pytest.mark.asyncio
async def test_refresh_unknown_token(service: AuthService) -> None:
    service.refresh_repository.get_by_token_hash_for_update = AsyncMock(
        return_value=None
    )

    with pytest.raises(InvalidTokenException) as exc_info:
        await service.refresh(refresh_token="unknown-token")

    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "INVALID_TOKEN"


@pytest.mark.asyncio
async def test_refresh_expired_token(service: AuthService) -> None:
    current = make_refresh_session(expires_at=datetime(2000, 1, 1))

    service.refresh_repository.get_by_token_hash_for_update = AsyncMock(
        return_value=current
    )
    service.refresh_repository.revoke = AsyncMock()

    with pytest.raises(TokenExpiredException) as exc_info:
        await service.refresh(refresh_token="expired-token")

    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "TOKEN_EXPIRED"
    assert exc_info.value.message == "Refresh token has expired"

    revoke_args, revoke_kwargs = (
        service.refresh_repository.revoke.await_args
    )
    assert revoke_args == (current,)
    assert isinstance(revoke_kwargs["revoked_at"], datetime)
    assert revoke_kwargs["revoked_at"].tzinfo is None


@pytest.mark.asyncio
async def test_refresh_replay_revokes_family(service: AuthService) -> None:
    current = make_refresh_session(revoked_at=datetime(2026, 1, 1))

    service.refresh_repository.get_by_token_hash_for_update = AsyncMock(
        return_value=current
    )
    service.refresh_repository.revoke_family = AsyncMock()

    with pytest.raises(InvalidTokenException) as exc_info:
        await service.refresh(refresh_token="replayed-token")

    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "INVALID_TOKEN"
    assert exc_info.value.message == "Refresh token reuse detected"

    family_args, family_kwargs = (
        service.refresh_repository.revoke_family.await_args
    )
    assert family_args == ("family-1",)
    assert isinstance(family_kwargs["revoked_at"], datetime)
    assert family_kwargs["revoked_at"].tzinfo is None


@pytest.mark.asyncio
async def test_refresh_rotates_token(service: AuthService) -> None:
    current = make_refresh_session()

    service.refresh_repository.get_by_token_hash_for_update = AsyncMock(
        return_value=current
    )
    service.user_repository.get_by_id = AsyncMock(
        return_value=make_user()
    )
    service.refresh_repository.create = AsyncMock(
        return_value=SimpleNamespace(id=2)
    )
    service.refresh_repository.revoke = AsyncMock()

    response = await service.refresh(
        refresh_token="valid-refresh-token"
    )

    assert response.refresh_token != "valid-refresh-token"

    claims = service.token_service.decode_access_token(
        response.access_token
    )
    assert claims.user_id == current.user_id

    create_kwargs = service.refresh_repository.create.await_args.kwargs
    assert create_kwargs["user_id"] == current.user_id
    assert create_kwargs["family_id"] == current.family_id
    assert len(create_kwargs["token_hash"]) == 64
    assert create_kwargs["token_hash"] != response.refresh_token

    revoke_args, revoke_kwargs = (
        service.refresh_repository.revoke.await_args
    )
    assert revoke_args == (current,)
    assert revoke_kwargs["replaced_by_id"] == 2


@pytest.mark.asyncio
async def test_refresh_revokes_family_for_inactive_user(
    service: AuthService,
) -> None:
    current = make_refresh_session()

    service.refresh_repository.get_by_token_hash_for_update = AsyncMock(
        return_value=current
    )
    service.user_repository.get_by_id = AsyncMock(
        return_value=make_user(is_active=False)
    )
    service.refresh_repository.revoke_family = AsyncMock()

    with pytest.raises(AuthenticationException) as exc_info:
        await service.refresh(refresh_token="valid-refresh-token")

    assert exc_info.value.message == "User account is inactive"

    service.refresh_repository.revoke_family.assert_awaited_once()


# Logout


@pytest.mark.asyncio
async def test_logout_revokes_family_and_commits(
    service: AuthService,
    session: MagicMock,
) -> None:
    current = make_refresh_session()

    service.refresh_repository.get_by_token_hash_for_update = AsyncMock(
        return_value=current
    )
    service.refresh_repository.revoke_family = AsyncMock()

    await service.logout(user_id=1, refresh_token="refresh-token")

    family_args, family_kwargs = (
        service.refresh_repository.revoke_family.await_args
    )
    assert family_args == ("family-1",)
    assert isinstance(family_kwargs["revoked_at"], datetime)

    session.commit.assert_awaited_once()
    session.begin.assert_not_called()


@pytest.mark.asyncio
async def test_logout_unknown_token_is_idempotent(
    service: AuthService,
    session: MagicMock,
) -> None:
    service.refresh_repository.get_by_token_hash_for_update = AsyncMock(
        return_value=None
    )
    service.refresh_repository.revoke_family = AsyncMock()

    await service.logout(user_id=1, refresh_token="unknown-token")

    service.refresh_repository.revoke_family.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.begin.assert_not_called()


@pytest.mark.asyncio
async def test_logout_does_not_revoke_other_users_session(
    service: AuthService,
    session: MagicMock,
) -> None:
    current = make_refresh_session(user_id=2)

    service.refresh_repository.get_by_token_hash_for_update = AsyncMock(
        return_value=current
    )
    service.refresh_repository.revoke_family = AsyncMock()

    await service.logout(user_id=1, refresh_token="other-token")

    service.refresh_repository.revoke_family.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_logout_already_revoked_token_is_idempotent(
    service: AuthService,
    session: MagicMock,
) -> None:
    current = make_refresh_session(revoked_at=datetime(2026, 1, 1))

    service.refresh_repository.get_by_token_hash_for_update = AsyncMock(
        return_value=current
    )
    service.refresh_repository.revoke_family = AsyncMock()

    await service.logout(user_id=1, refresh_token="revoked-token")

    service.refresh_repository.revoke_family.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_logout_propagates_revocation_failure(
    service: AuthService,
    session: MagicMock,
) -> None:
    current = make_refresh_session()

    service.refresh_repository.get_by_token_hash_for_update = AsyncMock(
        return_value=current
    )
    service.refresh_repository.revoke_family = AsyncMock(
        side_effect=RuntimeError("database unavailable")
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        await service.logout(user_id=1, refresh_token="refresh-token")

    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_logout_propagates_commit_failure(
    service: AuthService,
    session: MagicMock,
) -> None:
    current = make_refresh_session()

    service.refresh_repository.get_by_token_hash_for_update = AsyncMock(
        return_value=current
    )
    service.refresh_repository.revoke_family = AsyncMock()
    session.commit = AsyncMock(
        side_effect=RuntimeError("commit failed")
    )

    with pytest.raises(RuntimeError, match="commit failed"):
        await service.logout(user_id=1, refresh_token="refresh-token")


@pytest.mark.asyncio
async def test_logout_reuses_open_transaction_with_real_session(
    config: Settings,
) -> None:
    """Logout must not call begin() on an already open transaction."""
    session = AsyncSessionLocal()
    await session.begin()

    try:
        service = AuthService(session, config)
        current = make_refresh_session()

        service.refresh_repository.get_by_token_hash_for_update = (
            AsyncMock(return_value=current)
        )
        service.refresh_repository.revoke_family = AsyncMock()

        assert session.in_transaction() is True

        await service.logout(user_id=1, refresh_token="refresh-token")

        assert session.in_transaction() is False
        service.refresh_repository.revoke_family.assert_awaited_once()

    finally:
        await session.close()


@pytest.mark.asyncio
async def test_refresh_replay_commits_before_raising_with_real_session(
    config: Settings,
) -> None:
    """The family revocation transaction must commit before the 401."""
    session = AsyncSessionLocal()

    try:
        service = AuthService(session, config)
        current = make_refresh_session(revoked_at=datetime(2026, 1, 1))

        service.refresh_repository.get_by_token_hash_for_update = (
            AsyncMock(return_value=current)
        )
        service.refresh_repository.revoke_family = AsyncMock()

        with pytest.raises(InvalidTokenException):
            await service.refresh(refresh_token="replayed-token")

        assert session.in_transaction() is False

    finally:
        await session.close()


def test_refresh_token_hash_is_sha256() -> None:
    token = "example-refresh-token"

    digest = _hash_refresh_token(token)

    assert len(digest) == 64
    assert digest != token
