"""知识文档逻辑模型.

knowledge_documents 表示逻辑文档, 本身不直接参与检索. 检索只使用
current_published_version_id 指向的已发布版本. visibility 控制
PUBLIC/ADMIN_ONLY 访问边界.
"""

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
    """知识文档逻辑实体, 当前发布版本需要显式指定."""

    __tablename__ = "knowledge_documents"

    # 标题唯一; visibility/status 有数据库枚举约束, 避免非法状态进入检索.
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

    # PUBLIC 对所有登录用户可见, ADMIN_ONLY 只允许管理员检索.
    visibility: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="PUBLIC",
    )

    # ACTIVE/ARCHIVED/DELETED, 只有 ACTIVE 文档参与检索.
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="ACTIVE",
    )

    # 当前发布版本; NULL 表示文档尚无对外检索版本.
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

    # 版本按 version_no 排序, 便于展示发布历史和比较差异.
    versions: Mapped[list["KnowledgeDocumentVersion"]] = relationship(
        back_populates="document",
        order_by="KnowledgeDocumentVersion.version_no",
    )

    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="document",
    )
