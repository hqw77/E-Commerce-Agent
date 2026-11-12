
import asyncio

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException
from app.core.security import hash_password
from app.models.user import User, normalize_email
from app.repositories.user import UserRepository


class UserService:
    """
    Service for user-related business operations.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.user_repository = UserRepository(session)

    @staticmethod
    def _is_duplicate_email_error(exc: IntegrityError) -> bool:
        """
        Check whether an integrity error is caused by
        the unique constraint on the email column.
        """
        original_error = exc.orig
        error_args = getattr(original_error, "args", ())

        if not error_args or error_args[0] != 1062:
            return False

        error_message = (
            str(error_args[1]) if len(error_args) > 1 else ""
        )

        return "email" in error_message.lower()

    async def register_user(
        self,
        *,
        email: str,
        password: str,
    ) -> User:
        """
        Register a new user.

        Normalize the email, check for duplicates,
        hash the password, and create the user.

        Convert duplicate email database errors into
        ConflictException.
        """
        try:
            async with self.session.begin():
                normalized_email = normalize_email(email)

                existing_user = await self.user_repository.get_by_email(
                    normalized_email
                )

                if existing_user is not None:
                    raise ConflictException(
                        message="Email already registered",
                    )

                password_hash = await asyncio.to_thread(
                    hash_password,
                    password,
                )

                user = await self.user_repository.create(
                    email=normalized_email,
                    password_hash=password_hash,
                )

            return user

        except IntegrityError as exc:
            if self._is_duplicate_email_error(exc):
                raise ConflictException(
                    message="Email already registered",
                ) from exc

            raise
