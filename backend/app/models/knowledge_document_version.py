from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.knowledge_chunk import KnowledgeChunk
    from app.models.knowledge_document import KnowledgeDocument


class KnowledgeDocumentVersion(Base):
    """An immutable uploaded document version and its processing status."""

    __tablename__ = "knowledge_document_versions"

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "version_no",
            name="uq_knowledge_versions_document_version",
        ),
        Index("ix_knowledge_versions_document_status", "document_id", "status"),
        Index("ix_knowledge_versions_status", "status"),
        CheckConstraint(
            "status IN ('UPLOADED', 'PROCESSING', 'INDEXED', "
            "'PUBLISHED', 'SUPERSEDED', 'FAILED')",
            name="ck_knowledge_versions_status",
        ),
        CheckConstraint("version_no > 0", name="ck_knowledge_versions_version_no"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    document_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "knowledge_documents.id",
            name="fk_knowledge_versions_document",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )

    version_no: Mapped[int] = mapped_column(Integer, nullable=False)

    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)

    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)

    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)

    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)

    file_sha256: Mapped[str] = mapped_column(
        mysql.CHAR(64, charset="ascii", collation="ascii_bin"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="UPLOADED",
    )

    parser_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    chunking_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)

    embedding_dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)

    chunk_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
    )

    published_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
    )

    document: Mapped["KnowledgeDocument"] = relationship(
        back_populates="versions",
    )

    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="version",
        order_by="KnowledgeChunk.chunk_index",
    )
