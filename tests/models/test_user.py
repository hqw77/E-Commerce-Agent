import pytest

from app.models.user import normalize_email


@pytest.mark.parametrize(
    ("email", "expected"),
    [
        ("Alice@Example.com", "alice@example.com"),
        (" alice@example.com ", "alice@example.com"),
        ("ALICE@EXAMPLE.COM", "alice@example.com"),
        ("alice@example.com", "alice@example.com"),
    ],
)
def test_normalize_email(email: str, expected: str) -> None:
    assert normalize_email(email) == expected
