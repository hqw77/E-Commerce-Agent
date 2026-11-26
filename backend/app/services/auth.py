"""认证和会话生命周期 Service.

文件职责:
- 校验邮箱密码并签发 Access/Refresh Token.
- 轮换 Refresh Token 并检测重放.
- 登出时撤销整个 token family.

核心流程:
login -> 校验密码 -> 创建 refresh session
refresh -> 行锁 refresh -> 轮换并撤销旧 token
logout -> 撤销 family.
"""

import asyncio
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    AuthenticationException,
    InvalidTokenException,
    TokenExpiredException,
)
from app.core.security import verify_dummy_password, verify_password
from app.core.token import TokenService
from app.models.user import User, normalize_email
from app.repositories.refresh_session import RefreshSessionRepository
from app.repositories.user import UserRepository
from app.schemas.auth import TokenResponse


def _utc_now() -> datetime:
    """返回与 MySQL DATETIME 一致的 naive UTC 时间."""
    return datetime.now(UTC).replace(tzinfo=None)


def _hash_refresh_token(token: str) -> str:
    """对 Refresh Token 做 SHA-256, 数据库只保存哈希."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthService:
    """认证和会话生命周期业务服务."""

    def __init__(
        self,
        session: AsyncSession,
        config: Settings | None = None,
    ) -> None:
        """绑定 session, 配置和认证相关 Repository."""
        self.session = session
        self.config = config or get_settings()

        self.user_repository = UserRepository(session)
        self.refresh_repository = RefreshSessionRepository(session)
        self.token_service = TokenService(self.config)

    def _create_refresh_token(self) -> str:
        """生成高熵不透明 Refresh Token."""
        return secrets.token_urlsafe(48)

    def _build_token_response(
        self,
        user_id: int,
        refresh_token: str,
    ) -> TokenResponse:
        """签发 Access Token 并组装 TokenResponse."""
        access_token = self.token_service.create_access_token(user_id)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=self.config.jwt_access_token_expire_minutes * 60,
        )

    async def login(
        self,
        *,
        email: str,
        password: str,
    ) -> TokenResponse:
        """校验邮箱密码并创建 Refresh Session.

        Raises:
            AuthenticationException: 邮箱不存在, 密码错误或账号禁用.
        """
        async with self.session.begin():
            # ① 邮箱统一归一化后查询, 避免大小写重复账号.
            user = await self.user_repository.get_by_email(
                normalize_email(email)
            )

            if user is None:
                # Spend the same Argon2id work as a real verification so
                # that unknown emails and wrong passwords are not
                # distinguishable by response timing.
                await asyncio.to_thread(
                    verify_dummy_password,
                    password,
                )
                raise AuthenticationException(
                    message="Invalid email or password",
                )

            # ② Argon2id 校验是 CPU 密集型操作, 放到线程池.
            password_valid = await asyncio.to_thread(
                verify_password,
                password,
                user.password_hash,
            )

            if not password_valid or not user.is_active:
                raise AuthenticationException(
                    message="Invalid email or password",
                )

            # ③ 创建 refresh family, 数据库只保存 token 哈希.
            refresh_token = self._create_refresh_token()
            now = _utc_now()

            await self.refresh_repository.create(
                user_id=user.id,
                family_id=str(uuid4()),
                token_hash=_hash_refresh_token(refresh_token),
                expires_at=now + timedelta(
                    days=self.config.jwt_refresh_token_expire_days
                ),
            )

            response = self._build_token_response(
                user.id,
                refresh_token,
            )

        return response

    async def refresh(
        self,
        *,
        refresh_token: str,
    ) -> TokenResponse:
        """轮换 Refresh Token 并检测重放.

        重放检测必须在事务提交后再抛异常, 保证撤销已经持久化.
        """
        token_hash = _hash_refresh_token(refresh_token)
        now = _utc_now()

        replay_detected = False
        token_expired = False
        account_inactive = False
        response: TokenResponse | None = None

        async with self.session.begin():
            # ① 行锁当前 refresh 记录, 防止并发刷新同一 token.
            current = (
                await self.refresh_repository.get_by_token_hash_for_update(
                    token_hash
                )
            )

            if current is None:
                raise InvalidTokenException()

            if current.revoked_at is not None:
                # A consumed token was presented again.
                # Revoke all still-active sessions in this family.
                await self.refresh_repository.revoke_family(
                    current.family_id,
                    revoked_at=now,
                )
                replay_detected = True

            elif current.expires_at <= now:
                await self.refresh_repository.revoke(
                    current,
                    revoked_at=now,
                )
                token_expired = True

            else:
                user = await self.user_repository.get_by_id(
                    current.user_id
                )

                if user is None or not user.is_active:
                    await self.refresh_repository.revoke_family(
                        current.family_id,
                        revoked_at=now,
                    )
                    account_inactive = True
                else:
                    # ② 生成新 token, 旧 token 标记 replaced_by.
                    new_refresh_token = self._create_refresh_token()

                    new_session = await self.refresh_repository.create(
                        user_id=current.user_id,
                        family_id=current.family_id,
                        token_hash=_hash_refresh_token(
                            new_refresh_token
                        ),
                        expires_at=now + timedelta(
                            days=self.config.jwt_refresh_token_expire_days
                        ),
                    )

                    await self.refresh_repository.revoke(
                        current,
                        revoked_at=now,
                        replaced_by_id=new_session.id,
                    )

                    response = self._build_token_response(
                        user.id,
                        new_refresh_token,
                    )

        # These exceptions are raised after the transaction commits.
        # This is important: replay detection must persist revocation.
        if replay_detected:
            raise InvalidTokenException(
                message="Refresh token reuse detected",
            )

        if token_expired:
            raise TokenExpiredException(
                message="Refresh token has expired",
            )

        if account_inactive:
            raise AuthenticationException(
                message="User account is inactive",
            )

        if response is None:
            raise InvalidTokenException()

        return response

    async def logout(
        self,
        *,
        user_id: int,
        refresh_token: str,
    ) -> None:
        """撤销 Refresh Token 所属 family.

        未知或已撤销 token 保持幂等, 不泄露会话是否存在;
        不允许撤销其他用户的会话.
        """
        token_hash = _hash_refresh_token(refresh_token)
        now = _utc_now()

        current = (
            await self.refresh_repository.get_by_token_hash_for_update(
                token_hash
            )
        )

        # Logout is idempotent. Unknown or already-revoked tokens
        # do not reveal whether a session exists.
        if current is None:
            return

        # A caller must never revoke another user's session.
        if current.user_id != user_id:
            return

        await self.refresh_repository.revoke_family(
            current.family_id,
            revoked_at=now,
        )

        await self.session.commit()

    async def get_user_by_id(self, user_id: int) -> User:
        """读取可用用户, 不存在或禁用时按认证失败处理."""
        user = await self.user_repository.get_by_id(user_id)

        if user is None or not user.is_active:
            raise AuthenticationException(
                message="User account is unavailable",
            )

        return user
