
"""MySQL 异步连接和 Session 工厂.

Engine 由整个进程共享, 连接由连接池复用. 每次请求创建独立 AsyncSession,
它隔离事务和身份映射; 请求结束后关闭 Session, 但底层连接会归还连接池.
"""

from collections.abc import AsyncGenerator

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# 使用 asyncmy 驱动, 与异步 SQLAlchemy 搭配, 避免在 async 请求中执行同步数据库调用.
# 1. 构建 MySQL 异步连接 URL
DATABASE_URL = URL.create(
    drivername="mysql+asyncmy",
    username=settings.mysql_user,
    password=settings.mysql_password.get_secret_value(),
    host=settings.mysql_host,
    port=settings.mysql_port,
    database=settings.mysql_database,
    query={"charset": "utf8mb4"},
)


# pool_pre_ping 在借出连接前做健康检查, 避免 MySQL 主动断开后拿到死连接.
# pool_size 和 max_overflow 控制并发连接上限, 防止单进程耗尽数据库连接.
# 2. 创建异步数据库引擎
engine = create_async_engine(
    DATABASE_URL,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)


# expire_on_commit=False 避免提交后 ORM 属性立即过期, 减少异步代码中意外触发
# 隐式加载的概率; autoflush=False 让 Service 自己控制 flush 时机.
# 3. 创建异步 Session 工厂
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide an async database session.

    The session is automatically closed after the request finishes.

    get_db 不自动 commit. 原因是一个请求可能包含多个业务写操作,
    事务边界应由 Service 统一控制, 否则 Repository 各自提交会破坏原子性.
    """
    async with AsyncSessionLocal() as session:
        yield session