from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    """
    Schema for user registration requests.
    """

    email: EmailStr = Field(
        description="User email address.",
    )

    password: str = Field(
        min_length=8,
        max_length=128,
        description="User password.",
    )

class LoginRequest(BaseModel):
    """Schema for user login requests."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    """Schema for refresh-token requests."""

    refresh_token: str = Field(min_length=1, max_length=256)


class LogoutRequest(BaseModel):
    """Schema for logout requests."""

    refresh_token: str = Field(min_length=1, max_length=256)

class TokenResponse(BaseModel):
    """Token pair returned after login or refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int

class UserResponse(BaseModel):
    """
    Schema for user information responses.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int

    email: EmailStr

    is_active: bool