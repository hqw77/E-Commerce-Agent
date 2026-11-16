from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.knowledge_document import KnowledgeDocument
    from app.models.knowledge_document_version import KnowledgeDocumentVersion


class KnowledgeChunk(Base):
    """Authoritative chunk text; Qdrant stores only its vector and IDs."""

    __tablename__ = "knowledge_chunks"

    __table_args__ = (
        UniqueConstraint(
            "version_id",
            "chunk_index",
            name="uq_knowledge_chunks_version_index",
        ),
        Index("ix_knowledge_chunks_version_id", "version_id"),
        Index("ix_knowledge_chunks_content_hash", "content_hash"),
        CheckConstraint("chunk_index >= 0", name="ck_knowledge_chunks_index"),
        CheckConstraint("token_count > 0", name="ck_knowledge_chunks_tokens"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "knowledge_document_versions.id",
            name="fk_knowledge_chunks_version",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )

    document_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "knowledge_documents.id",
            name="fk_knowledge_chunks_document",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    content: Mapped[str] = mapped_column(mysql.LONGTEXT(), nullable=False)

    content_hash: Mapped[str] = mapped_column(
        mysql.CHAR(64, charset="ascii", collation="ascii_bin"),
        nullable=False,
    )

    token_count: Mapped[int] = mapped_column(Integer, nullable=False)

    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    section_title: Mapped[str | None] = mapped_column(String(500), nullable=True)

    start_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)

    end_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)

    chunk_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
    )

    document: Mapped["KnowledgeDocument"] = relationship(
        back_populates="chunks",
    )

    version: Mapped["KnowledgeDocumentVersion"] = relationship(
        back_populates="chunks",
    )
