"""认证 Service, 只签发 Access Token.

文件职责:
- 校验邮箱和密码.
- 签发短期 Access Token.
- 不再维护 Refresh Token 和会话表.

核心边界:
服务端不保存会话; 前端持有 Token, 过期后重新登录.
"""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import AuthenticationException
from app.core.security import verify_dummy_password, verify_password
from app.core.token import TokenService
from app.models.user import User, normalize_email
from app.repositories.user import UserRepository
from app.schemas.auth import TokenResponse


class AuthService:
    """认证业务服务."""

    def __init__(
        self,
        session: AsyncSession,
        config: Settings | None = None,
    ) -> None:
        """绑定 session, 配置和用户 Repository."""
        self.session = session
        self.config = config or get_settings()
        self.user_repository = UserRepository(session)
        self.token_service = TokenService(self.config)

    def _build_token_response(self, user_id: int) -> TokenResponse:
        """签发 Access Token 并组装响应."""
        access_token = self.token_service.create_access_token(user_id)

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=self.config.jwt_access_token_expire_minutes * 60,
        )

    async def login(
        self,
        *,
        email: str,
        password: str,
    ) -> TokenResponse:
        """校验邮箱密码并签发 Access Token.

        Raises:
            AuthenticationException: 邮箱不存在, 密码错误或账号禁用.
        """
        async with self.session.begin():
            # ① 邮箱统一归一化后查询, 避免大小写重复账号.
            user = await self.user_repository.get_by_email(
                normalize_email(email)
            )

            if user is None:
                # 用户不存在时也执行一次 Argon2id, 拉平登录耗时.
                await asyncio.to_thread(
                    verify_dummy_password,
                    password,
                )
                raise AuthenticationException(
                    message="Invalid email or password",
                )

            # ② Argon2id 校验是 CPU 密集操作, 放到线程池.
            password_valid = await asyncio.to_thread(
                verify_password,
                password,
                user.password_hash,
            )

            if not password_valid or not user.is_active:
                raise AuthenticationException(
                    message="Invalid email or password",
                )

            return self._build_token_response(user.id)

    async def get_user_by_id(self, user_id: int) -> User:
        """读取可用用户, 不存在或禁用时按认证失败处理."""
        user = await self.user_repository.get_by_id(user_id)

        if user is None or not user.is_active:
            raise AuthenticationException(
                message="User account is unavailable",
            )

        return user
