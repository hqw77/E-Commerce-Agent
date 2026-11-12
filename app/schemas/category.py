from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CategoryCreateRequest(BaseModel):
    """Payload for creating a category."""

    parent_id: int | None = Field(default=None, ge=1)
    name: str = Field(min_length=1, max_length=100)
    sort_order: int = Field(default=0, ge=0)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Category name must not be empty")

        return value


class CategoryUpdateRequest(BaseModel):
    """Payload for updating category name, order or status."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    sort_order: int | None = Field(default=None, ge=0)
    status: Literal["ENABLED", "DISABLED"] | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError("Category name must not be empty")

        return value


class CategoryResponse(BaseModel):
    """Category representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    parent_id: int | None
    name: str
    sort_order: int
    status: str
    created_at: datetime
    updated_at: datetime


class CategoryTreeNode(CategoryResponse):
    """Category node with nested children for tree responses."""

    children: list["CategoryTreeNode"] = Field(default_factory=list)
