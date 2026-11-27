from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.api.dependencies import get_current_user
from app.api.v1 import auth as auth_module
from app.core.config import Settings
from app.core.exceptions import ConflictException
from app.core.token import TokenService
from app.db.session import get_db
from app.main import app
from app.models.user import User
from app.services.auth import AuthService
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

TEST_JWT_SECRET = "test-secret-key-for-api-tests-at-least-32-bytes"


@pytest.fixture
def api_client():
    """Create a test client with an overridden database dependency."""
    session = MagicMock(spec=AsyncSession)

    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock(return_value=None)
    transaction.__aexit__ = AsyncMock(return_value=False)
    session.begin.return_value = transaction
    session.commit = AsyncMock()

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client, session
    app.dependency_overrides.pop(get_db, None)


def make_user(
    user_id: int = 1,
    email: str = "alice@example.com",
    is_active: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        email=email,
        password_hash="argon2-hashed-password",
        is_active=is_active,
        is_admin=False,
        is_debugger=False,
    )


@pytest.fixture
def api_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="testing",
        jwt_secret_key=TEST_JWT_SECRET,
    )


@pytest.fixture
def auth_service(api_client, api_settings, monkeypatch):
    """Bind the real AuthService to the overridden session."""
    _, session = api_client
    service = AuthService(session, api_settings)
    monkeypatch.setattr(auth_module, "AuthService", lambda _session: service)
    return service


@pytest.fixture
def authenticated_user():
    user = make_user()
    app.dependency_overrides[get_current_user] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_user, None)


def test_register_user_success(api_client, monkeypatch):
    """A valid registration should return HTTP 201."""
    client, _session = api_client
    expected_user = User(
        id=1,
        email="alice@example.com",
        password_hash="argon2-hashed-password",
        is_active=True,
    )
    user_service = MagicMock()
    user_service.register_user = AsyncMock(return_value=expected_user)
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
        "is_admin": False,
        "is_debugger": False,
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


def test_login_success(api_client, auth_service, api_settings):
    client, _ = api_client
    user = make_user()
    auth_service.user_repository.get_by_email = AsyncMock(return_value=user)

    with patch("app.services.auth.verify_password", return_value=True):
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": " Alice@Example.com ",
                "password": "Password123",
            },
        )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"

    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == (
        api_settings.jwt_access_token_expire_minutes * 60
    )
    assert body["access_token"]
    assert "refresh_token" not in body

    claims = TokenService(api_settings).decode_access_token(
        body["access_token"]
    )
    assert claims.user_id == user.id
    auth_service.user_repository.get_by_email.assert_awaited_once_with(
        "alice@example.com"
    )


def test_login_wrong_password_returns_401(api_client, auth_service):
    client, _ = api_client
    auth_service.user_repository.get_by_email = AsyncMock(
        return_value=make_user()
    )

    with patch("app.services.auth.verify_password", return_value=False):
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "alice@example.com",
                "password": "WrongPassword",
            },
        )

    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_FAILED"
    assert response.json()["message"] == "Invalid email or password"
    assert response.headers["www-authenticate"] == "Bearer"


def test_login_unknown_user_returns_uniform_failure(
    api_client,
    auth_service,
):
    client, _ = api_client
    auth_service.user_repository.get_by_email = AsyncMock(return_value=None)

    with patch("app.services.auth.verify_dummy_password") as dummy:
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "missing@example.com",
                "password": "Password123",
            },
        )

    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_FAILED"
    assert response.headers["www-authenticate"] == "Bearer"
    dummy.assert_called_once_with("Password123")


def test_login_inactive_user_returns_401(api_client, auth_service):
    client, _ = api_client
    auth_service.user_repository.get_by_email = AsyncMock(
        return_value=make_user(is_active=False)
    )

    with patch("app.services.auth.verify_password", return_value=True):
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "alice@example.com",
                "password": "Password123",
            },
        )

    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_FAILED"


def test_me_without_token_returns_401(api_client):
    client, _ = api_client
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_with_valid_token_returns_current_user(
    api_client,
    authenticated_user,
):
    client, _ = api_client
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.json()["id"] == authenticated_user.id
    assert response.json()["email"] == authenticated_user.email


def test_logout_requires_authentication(api_client):
    client, _ = api_client
    assert client.post("/api/v1/auth/logout").status_code == 401


def test_logout_returns_204(api_client, authenticated_user):
    client, _ = api_client
    assert client.post("/api/v1/auth/logout").status_code == 204
