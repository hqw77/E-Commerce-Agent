"""知识 Chunk 模型.

knowledge_chunks 保存权威文本和来源元数据, Qdrant 只保存对应向量和 ID.
检索命中向量后必须回查这里, 确保文本, 版本和权限仍然有效.
"""

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
    """知识片段权威文本, 是 RAG Source 的最终来源."""

    __tablename__ = "knowledge_chunks"

    # 同一版本内 chunk_index 唯一; 索引支持按版本和内容哈希查找.
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

    # 原文使用 LONGTEXT, 避免长文档被截断; 向量不在这里保存.
    content: Mapped[str] = mapped_column(mysql.LONGTEXT(), nullable=False)

    # 内容哈希用于去重和校验, 不代替业务主键.
    content_hash: Mapped[str] = mapped_column(
        mysql.CHAR(64, charset="ascii", collation="ascii_bin"),
        nullable=False,
    )

    token_count: Mapped[int] = mapped_column(Integer, nullable=False)

    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    section_title: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # 原文偏移量用于定位和调试切分结果.
    start_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)

    end_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 保存 chunking_version, unit_count 等非检索元数据.
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
