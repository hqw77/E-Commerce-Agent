
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import auth as auth_module
from app.core.exceptions import ConflictException
from app.db.session import get_db
from app.main import app
from app.models.user import User


@pytest.fixture
def api_client():
    """Create a test client with an overridden database dependency."""

    session = MagicMock(spec=AsyncSession)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db

    client = TestClient(app)

    yield client, session

    app.dependency_overrides.pop(get_db, None)


def test_register_user_success(api_client, monkeypatch):
    """A valid registration should return HTTP 201."""

    client, session = api_client

    expected_user = User(
        id=1,
        email="alice@example.com",
        password_hash="argon2-hashed-password",
        is_active=True,
    )

    user_service = MagicMock()
    user_service.register_user = AsyncMock(
        return_value=expected_user,
    )

    monkeypatch.setattr(
        auth_module,
        "UserService",
        lambda session: user_service,
    )

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "alice@example.com",
            "password": "MyPassword123",
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": 1,
        "email": "alice@example.com",
        "is_active": True,
    }

    assert "password_hash" not in response.json()

    user_service.register_user.assert_awaited_once_with(
        email="alice@example.com",
        password="MyPassword123",
    )


def test_register_user_invalid_email(api_client, monkeypatch):
    """An invalid email should return HTTP 422."""

    client, _ = api_client

    user_service = MagicMock()
    user_service.register_user = AsyncMock()

    monkeypatch.setattr(
        auth_module,
        "UserService",
        lambda session: user_service,
    )

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "invalid-email",
            "password": "MyPassword123",
        },
    )

    assert response.status_code == 422
    user_service.register_user.assert_not_awaited()


def test_register_user_short_password(api_client, monkeypatch):
    """A password shorter than 8 characters should return HTTP 422."""

    client, _ = api_client

    user_service = MagicMock()
    user_service.register_user = AsyncMock()

    monkeypatch.setattr(
        auth_module,
        "UserService",
        lambda session: user_service,
    )

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "alice@example.com",
            "password": "1234567",
        },
    )

    assert response.status_code == 422
    user_service.register_user.assert_not_awaited()


def test_register_user_duplicate_email(api_client, monkeypatch):
    """A duplicate email should return HTTP 409."""

    client, _ = api_client

    user_service = MagicMock()
    user_service.register_user = AsyncMock(
        side_effect=ConflictException(
            message="Email already registered",
        ),
    )

    monkeypatch.setattr(
        auth_module,
        "UserService",
        lambda session: user_service,
    )

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "alice@example.com",
            "password": "MyPassword123",
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "RESOURCE_CONFLICT"
    assert response.json()["message"] == "Email already registered"
