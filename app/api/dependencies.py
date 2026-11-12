
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AuthenticationException
from app.core.token import TokenService
from app.db.session import get_db
from app.models.user import User
from app.repositories.user import UserRepository

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Resolve the authenticated user from a bearer access token."""
    if credentials is None:
        raise AuthenticationException(
            message="Bearer access token is required",
        )

    token_service = TokenService(get_settings())
    claims = token_service.decode_access_token(
        credentials.credentials
    )

    repository = UserRepository(session)
    user = await repository.get_by_id(claims.user_id)

    if user is None or not user.is_active:
        raise AuthenticationException(
            message="User account is unavailable",
        )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
