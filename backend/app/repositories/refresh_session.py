
"""Refresh Token 会话 Repository.

文件职责:
- 按 token 哈希加锁读取.
- 创建 refresh session.
- 撤销单个 token 或整个 family.

核心边界:
数据库只保存 token 哈希, 明文只返回给客户端.
"""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_session import RefreshSession


class RefreshSessionRepository:
    """Refresh Token 会话表的数据库访问对象."""

    def __init__(self, session: AsyncSession) -> None:
        """初始化实例依赖."""
        self.session = session

    async def get_by_token_hash_for_update(
        self,
        token_hash: str,
    ) -> RefreshSession | None:
        """按哈希加行锁读取, 防止并发刷新同一 token."""
        statement = (
            select(RefreshSession)
            .where(RefreshSession.token_hash == token_hash)
            .with_for_update()
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: int,
        family_id: str,
        token_hash: str,
        expires_at: datetime,
    ) -> RefreshSession:
        """创建 refresh session, 只 flush 不 commit."""
        session = RefreshSession(
            user_id=user_id,
            family_id=family_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.session.add(session)
        await self.session.flush()
        return session

    async def revoke(
        self,
        session: RefreshSession,
        *,
        revoked_at: datetime,
        replaced_by_id: int | None = None,
    ) -> None:
        """标记单个 token 已撤销, 可记录被哪个新会话替换."""
        session.revoked_at = revoked_at
        session.replaced_by_id = replaced_by_id
        await self.session.flush()

    async def revoke_family(
        self,
        family_id: str,
        *,
        revoked_at: datetime,
    ) -> None:
        """撤销同一 family 下所有仍活跃的 token."""
        statement = (
            update(RefreshSession)
            .where(
                RefreshSession.family_id == family_id,
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )
        await self.session.execute(statement)
