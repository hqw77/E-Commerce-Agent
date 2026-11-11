
import pytest

from app.core.exceptions import (
    AppException,
    AuthenticationException,
    BusinessException,
    ConflictException,
    PermissionDeniedException,
    ResourceNotFoundException,
)


@pytest.mark.parametrize(
    ("exception", "expected_code", "expected_status"),
    [
        (
            BusinessException("商品库存不足"),
            "BUSINESS_ERROR",
            400,
        ),
        (
            AuthenticationException(),
            "AUTHENTICATION_FAILED",
            401,
        ),
        (
            PermissionDeniedException(),
            "PERMISSION_DENIED",
            403,
        ),
        (
            ResourceNotFoundException(),
            "RESOURCE_NOT_FOUND",
            404,
        ),
        (
            ConflictException(),
            "RESOURCE_CONFLICT",
            409,
        ),
    ],
)
def test_app_exception_attributes(
    exception: AppException,
    expected_code: str,
    expected_status: int,
) -> None:
    assert isinstance(exception, AppException)
    assert exception.code == expected_code
    assert exception.status_code == expected_status
    assert isinstance(exception.message, str)


def test_business_exception_custom_code() -> None:
    exception = BusinessException(
        message="商品库存不足",
        code="INSUFFICIENT_STOCK",
        details={"product_id": 1001},
    )

    assert exception.message == "商品库存不足"
    assert exception.code == "INSUFFICIENT_STOCK"
    assert exception.status_code == 400
    assert exception.details == {"product_id": 1001}


def test_app_exception_can_be_raised() -> None:
    with pytest.raises(ResourceNotFoundException) as exc_info:
        raise ResourceNotFoundException("订单不存在")

    assert str(exc_info.value) == "订单不存在"
