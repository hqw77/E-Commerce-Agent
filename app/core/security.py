import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# Create a shared password hasher.
_password_hasher = PasswordHasher()

# A fixed hash used to equalize login timing when the user does not exist.
# It is generated once per process, not on every request.
_DUMMY_PASSWORD_HASH = _password_hasher.hash(secrets.token_urlsafe(32))


def hash_password(plain_password: str) -> str:
    """
    Hash a plain-text password using Argon2id.

    A random salt is generated automatically.
    """
    return _password_hasher.hash(plain_password)


def verify_password(
    plain_password: str,
    password_hash: str,
) -> bool:
    """
    Verify a plain-text password against a stored password hash.

    Return False if the password does not match or the stored
    hash cannot be verified.
    """
    try:
        return _password_hasher.verify(
            password_hash,
            plain_password,
        )
    except (VerificationError, InvalidHashError):
        return False


def verify_dummy_password(plain_password: str) -> bool:
    """
    Run a password verification against a fixed dummy hash.

    The result is always False. Callers use this to spend the same
    Argon2id work whether or not the submitted email belongs to a
    registered user, which avoids leaking account existence through
    response timing.
    """
    try:
        _password_hasher.verify(
            _DUMMY_PASSWORD_HASH,
            plain_password,
        )
    except (VerificationError, InvalidHashError):
        return False

    return True


def needs_rehash(password_hash: str) -> bool:
    """
    Check whether a password hash needs to be upgraded.

    Compare the stored hash parameters with the current
    PasswordHasher configuration.
    """
    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except (VerificationError, InvalidHashError):
        return False
