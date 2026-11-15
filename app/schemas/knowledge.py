from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DocumentVisibility = Literal["PUBLIC", "ADMIN_ONLY"]
DocumentStatus = Literal["ACTIVE", "ARCHIVED", "DELETED"]
VersionStatus = Literal[
    "UPLOADED",
    "PROCESSING",
    "INDEXED",
    "PUBLISHED",
    "SUPERSEDED",
    "FAILED",
]


class DocumentResponse(BaseModel):
    """Knowledge document summary."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    visibility: DocumentVisibility
    status: DocumentStatus
    current_published_version_id: int | None
    created_by: int
    updated_by: int
    created_at: datetime
    updated_at: datetime


class VersionResponse(BaseModel):
    """Document version processing metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    version_no: int
    original_filename: str
    mime_type: str
    file_size: int
    file_sha256: str
    status: VersionStatus
    parser_version: str | None
    chunking_version: str | None
    embedding_model: str | None
    embedding_dimension: int | None
    chunk_count: int
    error_message: str | None
    created_at: datetime
    published_at: datetime | None


class DocumentDetailResponse(DocumentResponse):
    """Document with its version history."""

    versions: list[VersionResponse] = Field(default_factory=list)


class DocumentListResponse(BaseModel):
    """Paginated knowledge document list."""

    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int


class RetrievalRequest(BaseModel):
    """Knowledge retrieval request; identity is never accepted here."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Query must not be empty")

        return value


class RetrievalItem(BaseModel):
    """One retrieved chunk with traceable source metadata."""

    chunk_id: int
    document_id: int
    version_id: int
    document_title: str
    content: str
    score: float
    page_number: int | None
    section_title: str | None
    original_filename: str


class RetrievalResponse(BaseModel):
    """Top-K retrieval result."""

    items: list[RetrievalItem]
    total: int
