"""FastAPI 请求依赖.

依赖注入把认证, 数据库 Session 和管理员校验组合成可复用的类型别名.
业务 Router 只声明 CurrentUser/CurrentAdmin, 不重复解析 JWT.
"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import (
    AuthenticationException,
    PermissionDeniedException,
)
from app.core.token import TokenService
from app.db.session import get_db
from app.models.user import User
from app.repositories.user import UserRepository

# auto_error=False 让缺少 Authorization 头由业务异常体系统一处理,
# 而不是交给 FastAPI 默认的 403 响应.
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """从 Bearer Access Token 解析当前用户, 并确认账号仍然有效."""

    if credentials is None:
        raise AuthenticationException(
            message="Bearer access token is required",
        )

    # 只信任服务端校验后的 claims, 不从请求体或 Header 接收用户 ID.
    token_service = TokenService(get_settings())
    claims = token_service.decode_access_token(credentials.credentials)

    repository = UserRepository(session)
    user = await repository.get_by_id(claims.user_id)

    # token 可能还有效, 但用户已被禁用或删除, 因此每次请求都回查数据库.
    if user is None or not user.is_active:
        raise AuthenticationException(
            message="User account is unavailable",
        )

    return user


# 业务路由使用 Annotated 别名, 让 OpenAPI 和类型检查都能识别当前用户.
CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_admin(current_user: CurrentUser) -> User:
    """在已认证用户之上校验管理员权限, 普通用户返回 403."""

    if not current_user.is_admin:
        raise PermissionDeniedException(
            message="Administrator privileges are required",
        )

    return current_user


# 管理端路由使用 CurrentAdmin, 避免每个接口手写 is_admin 判断.
CurrentAdmin = Annotated[User, Depends(get_current_admin)]
