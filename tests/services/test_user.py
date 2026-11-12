
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException
from app.models.user import User
from app.services import user as user_service_module
from app.services.user import UserService


class MockTransaction:
    """Simulate an async database transaction context manager."""

    def __init__(self):
        self.exc_type = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self.exc_type = exc_type
        return False


@pytest.fixture
def service_dependencies(monkeypatch):
    """Prepare mocked dependencies for UserService tests."""

    session = MagicMock(spec=AsyncSession)

    transaction = MockTransaction()
    session.begin = MagicMock(return_value=transaction)

    repository = MagicMock()
    repository.get_by_email = AsyncMock()
    repository.create = AsyncMock()

    hash_password_mock = MagicMock(
        return_value="argon2-hashed-password"
    )

    monkeypatch.setattr(
        user_service_module,
        "UserRepository",
        lambda session: repository,
    )

    monkeypatch.setattr(
        user_service_module,
        "hash_password",
        hash_password_mock,
    )

    service = UserService(session)

    return {
        "session": session,
        "transaction": transaction,
        "repository": repository,
        "hash_password": hash_password_mock,
        "service": service,
    }


@pytest.mark.asyncio
async def test_register_user_success(service_dependencies):
    """A valid registration should create a user."""

    dependencies = service_dependencies
    repository = dependencies["repository"]

    expected_user = User(
        id=1,
        email="alice@example.com",
        password_hash="argon2-hashed-password",
        is_active=True,
    )

    repository.get_by_email.return_value = None
    repository.create.return_value = expected_user

    user = await dependencies["service"].register_user(
        email="alice@example.com",
        password="MyPassword123",
    )

    assert user is expected_user

    repository.get_by_email.assert_awaited_once_with(
        "alice@example.com"
    )

    dependencies["hash_password"].assert_called_once_with(
        "MyPassword123"
    )

    repository.create.assert_awaited_once_with(
        email="alice@example.com",
        password_hash="argon2-hashed-password",
    )

    assert dependencies["transaction"].exc_type is None


@pytest.mark.asyncio
async def test_register_user_normalizes_email(service_dependencies):
    """Registration should normalize the email address."""

    dependencies = service_dependencies
    repository = dependencies["repository"]

    repository.get_by_email.return_value = None

    expected_user = User(
        id=1,
        email="alice@example.com",
        password_hash="argon2-hashed-password",
        is_active=True,
    )

    repository.create.return_value = expected_user

    await dependencies["service"].register_user(
        email=" Alice@Example.com ",
        password="MyPassword123",
    )

    repository.get_by_email.assert_awaited_once_with(
        "alice@example.com"
    )

    repository.create.assert_awaited_once_with(
        email="alice@example.com",
        password_hash="argon2-hashed-password",
    )


@pytest.mark.asyncio
async def test_register_user_rejects_duplicate_email(
    service_dependencies,
):
    """Duplicate email should raise ConflictException."""

    dependencies = service_dependencies
    repository = dependencies["repository"]

    existing_user = User(
        id=1,
        email="alice@example.com",
        password_hash="existing-hash",
        is_active=True,
    )

    repository.get_by_email.return_value = existing_user

    with pytest.raises(ConflictException):
        await dependencies["service"].register_user(
            email="alice@example.com",
            password="MyPassword123",
        )

    dependencies["hash_password"].assert_not_called()
    repository.create.assert_not_awaited()

    assert dependencies["transaction"].exc_type is ConflictException


@pytest.mark.asyncio
async def test_register_user_rolls_back_on_create_error(
    service_dependencies,
):
    """An exception during user creation should leave the transaction uncommitted."""

    dependencies = service_dependencies
    repository = dependencies["repository"]

    repository.get_by_email.return_value = None
    repository.create.side_effect = RuntimeError(
        "Database operation failed"
    )

    with pytest.raises(RuntimeError):
        await dependencies["service"].register_user(
            email="alice@example.com",
            password="MyPassword123",
        )

    assert dependencies["transaction"].exc_type is RuntimeError

def test_duplicate_email_error_returns_true():
    """Test detection of MySQL duplicate email errors."""
    original_error = Exception(
        1062,
        "Duplicate entry 'alice@example.com' for key 'users.email'",
    )
    error = IntegrityError(
        statement="INSERT INTO users",
        params={},
        orig=original_error,
    )

    assert UserService._is_duplicate_email_error(error) is True


def test_other_duplicate_key_error_returns_false():
    """Test that other duplicate key errors are not treated as email conflicts."""
    original_error = Exception(
        1062,
        "Duplicate entry 'alice' for key 'users.username'",
    )
    error = IntegrityError(
        statement="INSERT INTO users",
        params={},
        orig=original_error,
    )

    assert UserService._is_duplicate_email_error(error) is False


def test_other_integrity_error_returns_false():
    """Test that non-duplicate integrity errors are not treated as email conflicts."""
    original_error = Exception(
        1452,
        "Cannot add or update a child row: a foreign key constraint fails",
    )
    error = IntegrityError(
        statement="INSERT INTO users",
        params={},
        orig=original_error,
    )

    assert UserService._is_duplicate_email_error(error) is False