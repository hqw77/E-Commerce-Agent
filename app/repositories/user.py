
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    """
    Repository for user database operations.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize the repository with a database session.
        """
        self.session = session

    async def get_by_email(self, email: str) -> User | None:
        """
        Retrieve a user by email address.

        Return None if the user does not exist.
        """
        statement = select(User).where(User.email == email)

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        email: str,
        password_hash: str,
    ) -> User:
        """
        Create a new user and flush it to the database.

        The transaction is managed by the service layer.
        """
        user = User(
            email=email,
            password_hash=password_hash,
        )

        self.session.add(user)

        await self.session.flush()

        return user
