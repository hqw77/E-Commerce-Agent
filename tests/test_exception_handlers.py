
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.exception_handlers import register_exception_handlers
from app.core.exceptions import (
    BusinessException,
    ResourceNotFoundException,
)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/business-error")
    async def business_error():
        raise BusinessException(
            message="商品库存不足",
            code="INSUFFICIENT_STOCK",
            details={"product_id": 1001},
        )

    @app.get("/not-found")
    async def not_found():
        raise ResourceNotFoundException("订单不存在")

    @app.get("/http-error")
    async def http_error():
        raise HTTPException(
            status_code=403,
            detail="Access denied",
        )

    @app.get("/validation/{product_id}")
    async def validation_error(product_id: int):
        return {"product_id": product_id}

    @app.get("/server-error")
    async def server_error():
        raise RuntimeError("database password leaked")

    return TestClient(app, raise_server_exceptions=False)


def test_business_exception_handler(client: TestClient) -> None:
    response = client.get("/business-error")

    assert response.status_code == 400
    assert response.json() == {
        "success": False,
        "code": "INSUFFICIENT_STOCK",
        "message": "商品库存不足",
        "details": {"product_id": 1001},
    }


def test_not_found_exception_handler(client: TestClient) -> None:
    response = client.get("/not-found")

    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"
    assert response.json()["message"] == "订单不存在"


def test_http_exception_handler(client: TestClient) -> None:
    response = client.get("/http-error")

    assert response.status_code == 403
    assert response.json()["code"] == "HTTP_ERROR"
    assert response.json()["message"] == "Access denied"


def test_validation_exception_handler(client: TestClient) -> None:
    response = client.get("/validation/abc")

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_unexpected_exception_handler(client: TestClient) -> None:
    response = client.get("/server-error")

    assert response.status_code == 500
    assert response.json() == {
        "success": False,
        "code": "INTERNAL_SERVER_ERROR",
        "message": "Internal server error",
        "details": None,
    }

    assert "database password leaked" not in response.text
