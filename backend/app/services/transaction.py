"""请求级数据库事务上下文.

文件职责:
- 如果当前 AsyncSession 已有事务, 复用并在结束时 commit/rollback.
- 如果没有事务, 开启一个新事务并在退出时提交.

核心边界:
Service 必须通过这个上下文组合多个 Repository 写操作, 不能各自 commit.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def transaction_context(
    session: AsyncSession,
) -> AsyncIterator[None]:
    """复用或创建事务, 保证异常时整体回滚.

    Args:
        session: 当前请求的 AsyncSession.

    Yields:
        None; 调用方在上下文中执行数据库操作.
    """
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
