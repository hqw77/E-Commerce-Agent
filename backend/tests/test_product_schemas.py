import pytest
from app.schemas.product import ProductCreateRequest, ProductUpdateRequest
from pydantic import ValidationError


def test_product_create_image_is_optional_and_normalized() -> None:
    request = ProductCreateRequest(
        product_no="P001",
        category_id=1,
        name="Phone",
    )
    assert request.image_url is None

    with_image = ProductCreateRequest(
        product_no="P002",
        category_id=1,
        name="Laptop",
        image_url="  /products/04-laptop.jpg  ",
    )
    assert with_image.image_url == "/products/04-laptop.jpg"


def test_product_update_image_can_be_cleared() -> None:
    request = ProductUpdateRequest(image_url="  ")
    assert request.image_url is None

    request = ProductUpdateRequest(product_no="  P003  ")
    assert request.product_no == "P003"


def test_product_image_path_length_is_bounded() -> None:
    with pytest.raises(ValidationError):
        ProductUpdateRequest(image_url="x" * 256)
