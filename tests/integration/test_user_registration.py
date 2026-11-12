
import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException
from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.repositories.user import UserRepository
from app.services.user import UserService


@pytest.mark.asyncio
async def test_concurrent_registration_with_same_email(monkeypatch):
    """
    Test concurrent registration with the same email
    using a real MySQL database.
    """
    email = f"{uuid4().hex}@example.com"
    password = "TestPassword123"

    # Synchronize both requests after their email checks.
    original_get_by_email = UserRepository.get_by_email

    arrivals = 0
    both_checked = asyncio.Event()

    async def synchronized_get_by_email(
        self: UserRepository,
        target_email: str,
    ) -> User | None:
        nonlocal arrivals

        user = await original_get_by_email(self, target_email)

        arrivals += 1

        if arrivals == 2:
            both_checked.set()

        await asyncio.wait_for(
            both_checked.wait(),
            timeout=10,
        )

        return user

    monkeypatch.setattr(
        UserRepository,
        "get_by_email",
        synchronized_get_by_email,
    )

    async def register() -> User:
        async with AsyncSessionLocal() as session:
            service = UserService(session)

            return await service.register_user(
                email=email,
                password=password,
            )

    try:
        results = await asyncio.gather(
            register(),
            register(),
            return_exceptions=True,
        )

        successful_results = [
            result
            for result in results
            if isinstance(result, User)
        ]

        conflict_results = [
            result
            for result in results
            if isinstance(result, ConflictException)
        ]

        assert len(successful_results) == 1
        assert len(conflict_results) == 1

        # Verify that only one user was persisted.
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(User).where(User.email == email)
            )
            users = result.scalars().all()

            assert len(users) == 1

    finally:
        # Remove test data to keep the database clean.
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(User).where(User.email == email)
            )
            await session.commit()
