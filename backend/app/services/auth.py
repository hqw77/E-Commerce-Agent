
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
    """Return current UTC time as a naive datetime for MySQL."""
    return datetime.now(UTC).replace(tzinfo=None)


def _hash_refresh_token(token: str) -> str:
    """Return the SHA-256 digest of a refresh token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthService:
    """Business service for authentication and session lifecycle."""

    def __init__(
        self,
        session: AsyncSession,
        config: Settings | None = None,
    ) -> None:
        self.session = session
        self.config = config or get_settings()

        self.user_repository = UserRepository(session)
        self.refresh_repository = RefreshSessionRepository(session)
        self.token_service = TokenService(self.config)

    def _create_refresh_token(self) -> str:
        """Generate a cryptographically secure opaque refresh token."""
        return secrets.token_urlsafe(48)

    def _build_token_response(
        self,
        user_id: int,
        refresh_token: str,
    ) -> TokenResponse:
        """Create a new access token and its response payload."""
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
        """Authenticate a user and create a refresh-token session."""
        async with self.session.begin():
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

            password_valid = await asyncio.to_thread(
                verify_password,
                password,
                user.password_hash,
            )

            if not password_valid or not user.is_active:
                raise AuthenticationException(
                    message="Invalid email or password",
                )

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
        """Rotate a refresh token and detect token replay."""
        token_hash = _hash_refresh_token(refresh_token)
        now = _utc_now()

        replay_detected = False
        token_expired = False
        account_inactive = False
        response: TokenResponse | None = None

        async with self.session.begin():
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
        """Revoke the session family associated with a refresh token.

        The request session usually has an active transaction because the
        authentication dependency loaded the current user. Reusing that
        transaction avoids "A transaction is already begun" errors, and
        the explicit commit makes the revocation durable.
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
        """Retrieve an active user for authenticated requests."""
        user = await self.user_repository.get_by_id(user_id)

        if user is None or not user.is_active:
            raise AuthenticationException(
                message="User account is unavailable",
            )

        return user
