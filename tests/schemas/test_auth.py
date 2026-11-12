
import pytest
from pydantic import ValidationError

from app.models.user import User
from app.schemas.auth import RegisterRequest, UserResponse


def test_register_request_success():
    """Valid registration data should pass validation."""
    request = RegisterRequest(
        email="alice@example.com",
        password="MyPassword123",
    )

    assert request.email == "alice@example.com"
    assert request.password == "MyPassword123"


def test_register_request_normalizes_email():
    """EmailStr should validate the email format."""
    request = RegisterRequest(
        email="alice@example.com",
        password="MyPassword123",
    )

    assert request.email == "alice@example.com"


def test_register_request_rejects_invalid_email():
    """Invalid email addresses should fail validation."""
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="invalid-email",
            password="MyPassword123",
        )


@pytest.mark.parametrize(
    "password",
    [
        "short",
        "1234567",
    ],
)
def test_register_request_rejects_short_password(password):
    """Passwords shorter than 8 characters should fail."""
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="alice@example.com",
            password=password,
        )


def test_register_request_rejects_long_password():
    """Passwords longer than 128 characters should fail."""
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="alice@example.com",
            password="a" * 129,
        )


def test_register_request_preserves_password():
    """Password whitespace should not be stripped automatically."""
    password = " MyPassword123 "

    request = RegisterRequest(
        email="alice@example.com",
        password=password,
    )

    assert request.password == password


def test_user_response_from_orm():
    """UserResponse should read attributes from a SQLAlchemy model."""
    user = User(
        id=1,
        email="alice@example.com",
        password_hash="hashed-password",
        is_active=True,
    )

    response = UserResponse.model_validate(user)

    assert response.id == 1
    assert response.email == "alice@example.com"
    assert response.is_active is True


def test_user_response_does_not_expose_password_hash():
    """Sensitive password hash must not appear in the response."""
    user = User(
        id=1,
        email="alice@example.com",
        password_hash="hashed-password",
        is_active=True,
    )

    response = UserResponse.model_validate(user)

    assert "password_hash" not in response.model_dump()
