
"""用户 Repository.

文件职责:
- 按邮箱或主键读取用户.
- 创建新用户.

核心边界:
这里只做 SQL, 密码哈希和重复邮箱业务由 UserService 处理.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    """用户表的数据库访问对象."""

    def __init__(self, session: AsyncSession) -> None:
        """绑定当前请求 session."""
        self.session = session

    async def get_by_email(self, email: str) -> User | None:
        """按已归一化邮箱读取用户."""
        statement = select(User).where(User.email == email)

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        """按主键读取用户."""
        statement = select(User).where(User.id == user_id)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        email: str,
        password_hash: str,
    ) -> User:
        """创建用户并 flush; 事务由 Service 控制."""
        user = User(
            email=email,
            password_hash=password_hash,
        )

        self.session.add(user)

        await self.session.flush()

        return user
