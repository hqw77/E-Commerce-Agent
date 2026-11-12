import asyncio
import hashlib
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.core.config import Settings
from app.core.exceptions import InvalidTokenException
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.refresh_session import RefreshSession
from app.models.user import User
from app.schemas.auth import TokenResponse
from app.services.auth import AuthService

TEST_PASSWORD = "IntegrationPassword123"
TEST_SECRET = "integration-test-secret-key-32-bytes"


@pytest.fixture
def auth_config() -> Settings:
    return Settings(
        _env_file=None,
        app_env="testing",
        jwt_secret_key=TEST_SECRET,
    )


async def create_test_user(email: str) -> int:
    password_hash = await asyncio.to_thread(
        hash_password,
        TEST_PASSWORD,
    )

    async with AsyncSessionLocal() as session:
        async with session.begin():
            user = User(
                email=email,
                password_hash=password_hash,
                is_active=True,
            )
            session.add(user)

        return user.id


async def delete_test_user(email: str) -> None:
    async with AsyncSessionLocal() as session, session.begin():
        result = await session.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()

        if user is None:
            return

        await session.execute(
            delete(RefreshSession).where(
                RefreshSession.user_id == user.id
            )
        )
        await session.execute(
            delete(User).where(User.id == user.id)
        )


async def fetch_sessions(user_id: int) -> list[SimpleNamespace]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(RefreshSession)
            .where(RefreshSession.user_id == user_id)
            .order_by(RefreshSession.id)
        )

        return [
            SimpleNamespace(
                id=row.id,
                family_id=row.family_id,
                token_hash=row.token_hash,
                revoked_at=row.revoked_at,
                expires_at=row.expires_at,
                replaced_by_id=row.replaced_by_id,
            )
            for row in result.scalars().all()
        ]


async def login(email: str, config: Settings) -> TokenResponse:
    async with AsyncSessionLocal() as session:
        service = AuthService(session, config)
        return await service.login(
            email=email,
            password=TEST_PASSWORD,
        )


async def refresh(token: str, config: Settings) -> TokenResponse:
    async with AsyncSessionLocal() as session:
        service = AuthService(session, config)
        return await service.refresh(refresh_token=token)


async def logout(
    user_id: int,
    refresh_token: str,
    config: Settings,
) -> None:
    async with AsyncSessionLocal() as session:
        service = AuthService(session, config)
        await service.logout(
            user_id=user_id,
            refresh_token=refresh_token,
        )


@pytest.mark.asyncio
async def test_login_refresh_and_replay_persist_revocation(
    auth_config: Settings,
) -> None:
    email = f"{uuid4().hex}@example.com"

    try:
        user_id = await create_test_user(email)

        tokens = await login(email, auth_config)
        assert tokens.access_token
        assert tokens.refresh_token

        sessions = await fetch_sessions(user_id)
        assert len(sessions) == 1

        first = sessions[0]
        expected_hash = hashlib.sha256(
            tokens.refresh_token.encode("utf-8")
        ).hexdigest()
        assert first.token_hash == expected_hash
        assert first.token_hash != tokens.refresh_token
        assert first.revoked_at is None
        assert first.expires_at > datetime.now(UTC).replace(tzinfo=None)

        rotated = await refresh(tokens.refresh_token, auth_config)
        assert rotated.refresh_token != tokens.refresh_token

        sessions = await fetch_sessions(user_id)
        assert len(sessions) == 2

        first, second = sessions
        assert first.revoked_at is not None
        assert first.replaced_by_id == second.id
        assert second.revoked_at is None

        with pytest.raises(InvalidTokenException) as exc_info:
            await refresh(tokens.refresh_token, auth_config)

        assert exc_info.value.code == "INVALID_TOKEN"
        assert exc_info.value.message == "Refresh token reuse detected"

        # A fresh session must observe the committed family revocation.
        sessions = await fetch_sessions(user_id)
        assert len(sessions) == 2
        assert all(row.revoked_at is not None for row in sessions)

    finally:
        await delete_test_user(email)


@pytest.mark.asyncio
async def test_logout_revokes_family_and_is_idempotent(
    auth_config: Settings,
) -> None:
    email = f"{uuid4().hex}@example.com"

    try:
        user_id = await create_test_user(email)
        tokens = await login(email, auth_config)

        await logout(user_id, tokens.refresh_token, auth_config)

        sessions = await fetch_sessions(user_id)
        assert len(sessions) == 1
        assert sessions[0].revoked_at is not None

        # Logging out again must stay idempotent and keep the session revoked.
        await logout(user_id, tokens.refresh_token, auth_config)

        sessions = await fetch_sessions(user_id)
        assert len(sessions) == 1
        assert sessions[0].revoked_at is not None

    finally:
        await delete_test_user(email)


@pytest.mark.asyncio
async def test_concurrent_refresh_allows_single_rotation(
    auth_config: Settings,
) -> None:
    email = f"{uuid4().hex}@example.com"

    try:
        user_id = await create_test_user(email)
        tokens = await login(email, auth_config)

        results = await asyncio.gather(
            refresh(tokens.refresh_token, auth_config),
            refresh(tokens.refresh_token, auth_config),
            return_exceptions=True,
        )

        successes = [
            result
            for result in results
            if isinstance(result, TokenResponse)
        ]
        failures = [
            result
            for result in results
            if isinstance(result, InvalidTokenException)
        ]

        assert len(successes) == 1
        assert len(failures) == 1

        sessions = await fetch_sessions(user_id)

        # One login session plus one rotated session, and no second
        # successful rotation may leave an active refresh token behind.
        assert len(sessions) == 2
        assert all(row.revoked_at is not None for row in sessions)

    finally:
        await delete_test_user(email)
