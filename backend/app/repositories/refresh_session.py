
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_session import RefreshSession


class RefreshSessionRepository:
    """Repository for refresh-token session persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_token_hash_for_update(
        self,
        token_hash: str,
    ) -> RefreshSession | None:
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
        session.revoked_at = revoked_at
        session.replaced_by_id = replaced_by_id
        await self.session.flush()

    async def revoke_family(
        self,
        family_id: str,
        *,
        revoked_at: datetime,
    ) -> None:
        statement = (
            update(RefreshSession)
            .where(
                RefreshSession.family_id == family_id,
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )
        await self.session.execute(statement)
