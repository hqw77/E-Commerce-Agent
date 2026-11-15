from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
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
    from app.models.knowledge_document_version import KnowledgeDocumentVersion


class KnowledgeDocument(Base):
    """Logical knowledge document; its current version is published explicitly."""

    __tablename__ = "knowledge_documents"

    __table_args__ = (
        UniqueConstraint("title", name="uq_knowledge_documents_title"),
        Index("ix_knowledge_documents_status", "status"),
        Index("ix_knowledge_documents_visibility", "visibility"),
        CheckConstraint(
            "visibility IN ('PUBLIC', 'ADMIN_ONLY')",
            name="ck_knowledge_documents_visibility",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'ARCHIVED', 'DELETED')",
            name="ck_knowledge_documents_status",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    visibility: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="PUBLIC",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="ACTIVE",
    )

    current_published_version_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    created_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            name="fk_knowledge_documents_created_by",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )

    updated_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            name="fk_knowledge_documents_updated_by",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
    )

    updated_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)"),
    )

    versions: Mapped[list["KnowledgeDocumentVersion"]] = relationship(
        back_populates="document",
        order_by="KnowledgeDocumentVersion.version_no",
    )

    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="document",
    )
