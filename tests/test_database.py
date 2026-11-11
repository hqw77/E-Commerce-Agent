import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal, engine, get_db


@pytest.mark.asyncio
async def test_database_connection():
    """Test whether MySQL is reachable."""
    async with engine.connect() as connection:
        result = await connection.execute(text("SELECT 1"))
        assert result.scalar_one() == 1


@pytest.mark.asyncio
async def test_session_factory():
    """Test whether an async session can be created."""
    async with AsyncSessionLocal() as session:
        assert isinstance(session, AsyncSession)



@pytest.mark.asyncio
async def test_get_db_dependency():
    """Test database dependency lifecycle."""
    generator = get_db()

    session = await anext(generator)
    assert isinstance(session, AsyncSession)

    # 创建一个事务，验证依赖结束时事务得到清理
    await session.begin()
    assert session.in_transaction()

    # 关闭依赖生成器，触发 async with 的退出逻辑
    await generator.aclose()

    # Session 退出后，事务应该已经结束
    assert not session.in_transaction()
