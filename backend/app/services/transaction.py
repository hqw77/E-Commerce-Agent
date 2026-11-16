from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def transaction_context(
    session: AsyncSession,
) -> AsyncIterator[None]:
    """Reuse an existing request transaction or open a new one."""
    if session.in_transaction():
        try:
            yield
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    else:
        async with session.begin():
            yield
