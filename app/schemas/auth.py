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


class UserResponse(BaseModel):
    """
    Schema for user information responses.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int

    email: EmailStr

    is_active: bool