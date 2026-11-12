
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
    """Register a new user account."""
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
    """Authenticate a user and issue access and refresh tokens."""
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
    """Rotate a refresh token and issue a new token pair."""
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
    """Return the current authenticated user's public profile."""
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
    """Revoke the current user's refresh-token session family."""
    service = AuthService(session)

    await service.logout(
        user_id=current_user.id,
        refresh_token=request.refresh_token,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
