
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Create a test client without starting application lifespan."""
    return TestClient(app)


@pytest.fixture
def mock_dependencies(monkeypatch):
    """Mock successful MySQL and Redis connections."""

    # Mock MySQL connection.
    connection = AsyncMock()

    connection_context = MagicMock()
    connection_context.__aenter__ = AsyncMock(
        return_value=connection
    )
    connection_context.__aexit__ = AsyncMock(
        return_value=False
    )

    mock_engine = SimpleNamespace(
        connect=MagicMock(return_value=connection_context)
    )

    monkeypatch.setattr(
        "app.api.v1.health.engine",
        mock_engine,
    )

    # Mock Redis connection.
    mock_redis = SimpleNamespace(
        ping=AsyncMock(return_value=True)
    )

    monkeypatch.setattr(
        "app.api.v1.health.redis_client",
        mock_redis,
    )

    return mock_engine, mock_redis


def test_health_live(client: TestClient) -> None:
    """Test application liveness endpoint."""

    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_ready_success(
    client: TestClient,
    mock_dependencies,
) -> None:
    """Test readiness when all dependencies are available."""

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {
            "database": "ok",
            "redis": "ok",
        },
    }


def test_health_ready_database_failure(
    client: TestClient,
    mock_dependencies,
    monkeypatch,
) -> None:
    """Test readiness when MySQL is unavailable."""

    mock_engine = SimpleNamespace(
        connect=MagicMock(
            side_effect=SQLAlchemyError("Database unavailable")
        )
    )

    monkeypatch.setattr(
        "app.api.v1.health.engine",
        mock_engine,
    )

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["checks"]["database"] == "error"
    assert response.json()["checks"]["redis"] == "ok"


def test_health_ready_redis_failure(
    client: TestClient,
    mock_dependencies,
    monkeypatch,
) -> None:
    """Test readiness when Redis is unavailable."""

    mock_redis = SimpleNamespace(
        ping=AsyncMock(
            side_effect=RedisError("Redis unavailable")
        )
    )

    monkeypatch.setattr(
        "app.api.v1.health.redis_client",
        mock_redis,
    )

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["checks"]["database"] == "ok"
    assert response.json()["checks"]["redis"] == "error"


def test_health_ready_all_dependencies_failure(
    client: TestClient,
    monkeypatch,
) -> None:
    """Test readiness when both MySQL and Redis are unavailable."""

    mock_engine = SimpleNamespace(
        connect=MagicMock(
            side_effect=SQLAlchemyError("Database unavailable")
        )
    )

    mock_redis = SimpleNamespace(
        ping=AsyncMock(
            side_effect=RedisError("Redis unavailable")
        )
    )

    monkeypatch.setattr(
        "app.api.v1.health.engine",
        mock_engine,
    )

    monkeypatch.setattr(
        "app.api.v1.health.redis_client",
        mock_redis,
    )

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {
            "database": "error",
            "redis": "error",
        },
    }
