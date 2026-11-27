"""认证请求/响应 Schema."""

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    """注册请求."""

    email: EmailStr = Field(
        description="User email address.",
    )

    password: str = Field(
        min_length=8,
        max_length=128,
        description="User password.",
    )


class LoginRequest(BaseModel):
    """登录请求."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    """登录响应, 只包含 Access Token."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    """当前用户公开信息."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    is_active: bool
    is_admin: bool = False
    is_debugger: bool = False

    @field_validator("is_admin", "is_debugger", mode="before")
    @classmethod
    def normalize_flags(cls, value: object) -> bool:
        """把 ORM 权限字段整理成响应结构."""
        return bool(value)
