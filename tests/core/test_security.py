from app.core.security import hash_password, needs_rehash, verify_password


def test_hash_password() -> None:
    password = "MyPassword123"

    password_hash = hash_password(password)

    assert password_hash != password
    assert password_hash.startswith("$argon2id$")


def test_verify_password_success() -> None:
    password = "MyPassword123"

    password_hash = hash_password(password)

    assert verify_password(password, password_hash) is True


def test_verify_password_failure() -> None:
    password = "MyPassword123"

    password_hash = hash_password(password)

    assert verify_password("WrongPassword", password_hash) is False


def test_hash_password_generates_different_hashes() -> None:
    password = "MyPassword123"

    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert first_hash != second_hash


def test_verify_password_with_invalid_hash() -> None:
    assert verify_password("MyPassword123", "invalid-hash") is False


def test_needs_rehash_with_current_hash() -> None:
    password_hash = hash_password("MyPassword123")

    assert needs_rehash(password_hash) is False


def test_needs_rehash_with_invalid_hash() -> None:
    assert needs_rehash("invalid-hash") is False
