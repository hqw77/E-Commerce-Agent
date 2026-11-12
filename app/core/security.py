from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# Create a shared password hasher.
_password_hasher = PasswordHasher()


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
