
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.auth import RegisterRequest, UserResponse
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
    """
    Register a new user account.
    """
    user_service = UserService(session)

    user = await user_service.register_user(
        email=request.email,
        password=request.password,
    )

    return UserResponse.model_validate(user)
