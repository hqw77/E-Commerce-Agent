"""知识文档版本模型.

每个版本对应一次上传文件, 保存文件元数据, 解析/切分/Embedding 版本和
处理状态. 版本内容不可原地覆盖, 新内容必须创建新版本.
"""

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
    """不可变的文档版本及其处理状态."""

    __tablename__ = "knowledge_document_versions"

    # 同一文档版本号递增唯一; status 约束限制处理状态机.
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

    # 原始文件存储键, 与数据库记录分离, 便于替换存储实现.
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)

    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)

    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # 文件内容哈希, 用于完整性校验和判断重复上传.
    file_sha256: Mapped[str] = mapped_column(
        mysql.CHAR(64, charset="ascii", collation="ascii_bin"),
        nullable=False,
    )

    # UPLOADED/PROCESSING/INDEXED/PUBLISHED/SUPERSEDED/FAILED.
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="UPLOADED",
    )

    # 记录解析, 切分和 Embedding 版本, 便于复现和回滚处理结果.
    parser_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    chunking_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)

    embedding_dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 处理完成后写入 Chunk 数量, 用于校验索引和快速展示.
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
