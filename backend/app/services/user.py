"""用户注册 Service.

文件职责:
- 归一化邮箱并检查重复.
- 用 Argon2id 哈希密码.
- 把数据库唯一键冲突转换为业务冲突.

核心边界:
用户注册只创建账号; 登录和 Token 由 AuthService 负责.
"""

import asyncio

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException
from app.core.security import hash_password
from app.models.user import User, normalize_email
from app.repositories.user import UserRepository


class UserService:
    """用户注册相关业务操作."""

    def __init__(self, session: AsyncSession) -> None:
        """绑定当前请求 session 和用户 Repository."""
        self.session = session
        self.user_repository = UserRepository(session)

    @staticmethod
    def _is_duplicate_email_error(exc: IntegrityError) -> bool:
        """判断 MySQL 1062 是否来自 email 唯一约束."""
        original_error = exc.orig
        error_args = getattr(original_error, "args", ())

        if not error_args or error_args[0] != 1062:
            return False

        error_message = (
            str(error_args[1]) if len(error_args) > 1 else ""
        )

        return "email" in error_message.lower()

    async def register_user(
        self,
        *,
        email: str,
        password: str,
    ) -> User:
        """注册新用户.

        Raises:
            ConflictException: 邮箱已注册.
        """
        try:
            async with self.session.begin():
                # ① 邮箱统一小写去空白, 防止大小写重复注册.
                normalized_email = normalize_email(email)

                existing_user = await self.user_repository.get_by_email(
                    normalized_email
                )

                if existing_user is not None:
                    raise ConflictException(
                        message="Email already registered",
                    )

                # ② Argon2id 哈希是 CPU 密集操作, 放到线程池.
                password_hash = await asyncio.to_thread(
                    hash_password,
                    password,
                )

                user = await self.user_repository.create(
                    email=normalized_email,
                    password_hash=password_hash,
                )

            return user

        except IntegrityError as exc:
            # ③ 并发注册可能同时通过预检查, 依赖数据库唯一键兜底.
            if self._is_duplicate_email_error(exc):
                raise ConflictException(
                    message="Email already registered",
                ) from exc

            raise
