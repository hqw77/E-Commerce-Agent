
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.user import UserRepository


@pytest.fixture
def mock_session():
    """Create a mocked async database session."""
    session = MagicMock(spec=AsyncSession)

    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    return session


@pytest.fixture
def user_repository(mock_session):
    """Create a UserRepository with a mocked session."""
    return UserRepository(mock_session)


@pytest.mark.asyncio
async def test_get_by_email_returns_user(
    mock_session,
    user_repository,
):
    """Should return a user when the email exists."""
    expected_user = User(
        id=1,
        email="alice@example.com",
        password_hash="hashed-password",
        is_active=True,
    )

    result = MagicMock()
    result.scalar_one_or_none.return_value = expected_user

    mock_session.execute.return_value = result

    user = await user_repository.get_by_email(
        "alice@example.com"
    )

    assert user is expected_user
    mock_session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_by_email_returns_none(
    mock_session,
    user_repository,
):
    """Should return None when the email does not exist."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = None

    mock_session.execute.return_value = result

    user = await user_repository.get_by_email(
        "unknown@example.com"
    )

    assert user is None


@pytest.mark.asyncio
async def test_create_user(
    mock_session,
    user_repository,
):
    """Should create a user and flush the session."""
    user = await user_repository.create(
        email="alice@example.com",
        password_hash="hashed-password",
    )

    assert isinstance(user, User)
    assert user.email == "alice@example.com"
    assert user.password_hash == "hashed-password"

    mock_session.add.assert_called_once_with(user)
    mock_session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_does_not_commit(
    mock_session,
    user_repository,
):
    """Repository should not commit the transaction."""
    await user_repository.create(
        email="alice@example.com",
        password_hash="hashed-password",
    )

    mock_session.commit.assert_not_awaited()
