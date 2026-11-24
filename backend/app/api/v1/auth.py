
"""认证 API.

这一层只负责 HTTP 协议和依赖注入, 具体的密码校验, Refresh 轮换和会话撤销
全部委托给 AuthService/UserService. 这样认证规则不会散落在 Router 中.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.db.session import get_db
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth import AuthService
from app.services.user import UserService

router = APIRouter()


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register_user(
    request: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """注册新用户. 邮箱唯一性和密码哈希由 UserService 负责."""
    user_service = UserService(session)

    user = await user_service.register_user(
        email=request.email,
        password=request.password,
    )

    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Login and obtain tokens",
)
async def login(
    request: LoginRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """登录并签发 Access/Refresh Token."""
    # 登录响应包含 token, 禁止浏览器或中间代理缓存.
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"

    service = AuthService(session)

    return await service.login(
        email=request.email,
        password=request.password,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate refresh token",
)
async def refresh_tokens(
    request: RefreshRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """轮换 Refresh Token. 旧 token 被消费, 新 token 继续沿用同一 family."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"

    service = AuthService(session)

    return await service.refresh(
        refresh_token=request.refresh_token,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user",
)
async def get_me(
    current_user: CurrentUser,
) -> UserResponse:
    """返回当前登录用户的公开资料. 用户身份来自 CurrentUser, 不接受请求体指定."""
    return UserResponse.model_validate(current_user)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout and revoke session",
)
async def logout(
    request: LogoutRequest,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """退出登录并撤销当前 Refresh Token 所在的整个 family."""
    service = AuthService(session)

    await service.logout(
        user_id=current_user.id,
        refresh_token=request.refresh_token,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
