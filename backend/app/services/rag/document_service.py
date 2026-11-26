"""知识文档和版本的导入, 索引, 发布与删除.

文件职责:
- 校验上传文件并保存到本地存储.
- 创建文档和版本记录.
- 解析, 清洗, Chunk, Embedding 并写入 Qdrant.
- 发布版本和软删除文档.

核心流程:
create_document -> process_version -> parse/clean/chunk/embed
-> MySQL chunks + Qdrant points -> publish_version.
"""

import asyncio
import hashlib
import logging
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    ConflictException,
    PermissionDeniedException,
    ResourceNotFoundException,
    ValidationException,
)
from app.infrastructure.storage.local import LocalFileStorage
from app.infrastructure.vector.qdrant import QdrantVectorStore, VectorPoint
from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_document_version import KnowledgeDocumentVersion
from app.models.user import User
from app.repositories.knowledge import (
    KnowledgeChunkRepository,
    KnowledgeDocumentRepository,
    KnowledgeVersionRepository,
)
from app.services.rag.chunker import Chunker
from app.services.rag.embedding import BgeM3EmbeddingProvider
from app.services.rag.parser import PARSER_VERSION, DocumentParser
from app.services.rag.text_cleaner import clean_documents
from app.services.transaction import transaction_context

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """返回不带时区信息的 UTC 时间, 与 MySQL 保持一致."""
    return datetime.now(UTC).replace(tzinfo=None)


class KnowledgeDocumentService:
    """知识文档和版本生命周期编排."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings | None = None,
        *,
        storage: LocalFileStorage | None = None,
        parser: DocumentParser | None = None,
        chunker: Chunker | None = None,
        embedding: BgeM3EmbeddingProvider | None = None,
        vector_store: QdrantVectorStore | None = None,
    ) -> None:
        """初始化存储, 解析, 切分, Embedding 和向量依赖."""
        self.session = session
        self.settings = settings or get_settings()
        self.storage = storage or LocalFileStorage(self.settings)
        self.parser = parser or DocumentParser()
        self.chunker = chunker or Chunker(self.settings)
        self.embedding = embedding or BgeM3EmbeddingProvider(self.settings)
        self.vector_store = vector_store or QdrantVectorStore(self.settings)
        self.documents = KnowledgeDocumentRepository(session)
        self.versions = KnowledgeVersionRepository(session)
        self.chunks = KnowledgeChunkRepository(session)

    @staticmethod
    def _require_admin(user: User) -> None:
        """校验知识库管理权限."""
        if not user.is_admin:
            raise PermissionDeniedException(
                message="Administrator privileges are required",
            )

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        """只记录异常类型, 不把内部细节写入版本错误信息."""
        return f"Knowledge processing failed ({type(exc).__name__})"

    async def _load_file(self, filename: str, content: bytes) -> tuple[bytes, str]:
        """校验文件大小, 类型并计算内容 hash."""
        max_bytes = self.settings.rag_max_file_size_mb * 1024 * 1024
        if len(content) > max_bytes:
            raise ValidationException(
                message="Knowledge document exceeds size limit",
                code="KNOWLEDGE_FILE_TOO_LARGE",
            )
        self.parser.validate_file(filename, content)
        return content, hashlib.sha256(content).hexdigest()

    async def create_document(
        self,
        *,
        user: User,
        title: str,
        description: str | None,
        visibility: str,
        original_filename: str,
        content: bytes,
    ) -> KnowledgeDocument:
        """创建文档及其第一个版本, 并立即触发索引.

        Args:
            user: 当前管理员.
            title: 文档标题, 全局唯一.
            description: 文档描述.
            visibility: PUBLIC 或 ADMIN_ONLY.
            original_filename: 原始文件名.
            content: 文件字节.

        Returns:
            含版本列表的 KnowledgeDocument.

        Raises:
            ValidationException: 标题, 可见性或文件不合法.
            ConflictException: 标题重复.
        """
        self._require_admin(user)
        title = title.strip()
        if not title:
            raise ValidationException(
                message="Document title must not be empty",
                code="KNOWLEDGE_TITLE_REQUIRED",
            )
        if visibility not in {"PUBLIC", "ADMIN_ONLY"}:
            raise ValidationException(
                message="Invalid document visibility",
                code="KNOWLEDGE_VISIBILITY_INVALID",
            )

        # ① 校验文件并写入本地存储, 数据库只保存 storage_key.
        content, file_sha256 = await self._load_file(original_filename, content)
        storage_key = await self.storage.save(content, original_filename)
        mime_type = self.parser.mime_type_for(original_filename)

        try:
            # ② 文档和初始版本必须在同一事务中创建.
            async with transaction_context(self.session):
                if await self.documents.get_by_title(title) is not None:
                    raise ConflictException(
                        message="Knowledge document title already exists",
                        code="KNOWLEDGE_TITLE_CONFLICT",
                    )
                document = await self.documents.create(
                    title=title,
                    description=description,
                    visibility=visibility,
                    created_by=user.id,
                )
                version = await self.versions.create(
                    document_id=document.id,
                    version_no=1,
                    original_filename=original_filename,
                    storage_key=storage_key,
                    mime_type=mime_type,
                    file_size=len(content),
                    file_sha256=file_sha256,
                )
        except IntegrityError as exc:
            raise ConflictException(
                message="Knowledge document title already exists",
                code="KNOWLEDGE_TITLE_CONFLICT",
            ) from exc

        # ③ 索引失败时版本状态为 FAILED, 文档记录保留以便 retry.
        await self.process_version(document.id, version.id)
        refreshed = await self.documents.get_by_id(document.id, with_versions=True)
        assert refreshed is not None
        return refreshed

    async def create_version(
        self,
        *,
        user: User,
        document_id: int,
        original_filename: str,
        content: bytes,
    ) -> KnowledgeDocument:
        """为已有 ACTIVE 文档创建新版本并触发索引."""
        self._require_admin(user)
        document = await self.documents.get_by_id(document_id)
        if document is None or document.status == "DELETED":
            raise ResourceNotFoundException(
                message="Knowledge document not found",
                code="KNOWLEDGE_DOCUMENT_NOT_FOUND",
            )
        if document.status != "ACTIVE":
            raise ConflictException(
                message="Knowledge document is not active",
                code="KNOWLEDGE_DOCUMENT_NOT_ACTIVE",
            )

        content, file_sha256 = await self._load_file(original_filename, content)
        storage_key = await self.storage.save(content, original_filename)
        mime_type = self.parser.mime_type_for(original_filename)

        # ① 行锁保证同一文档的 version_no 不并发冲突.
        async with transaction_context(self.session):
            await self.documents.get_by_id(document_id, for_update=True)
            version_no = await self.versions.get_next_version_no(document_id)
            version = await self.versions.create(
                document_id=document_id,
                version_no=version_no,
                original_filename=original_filename,
                storage_key=storage_key,
                mime_type=mime_type,
                file_size=len(content),
                file_sha256=file_sha256,
            )

        await self.process_version(document_id, version.id)
        refreshed = await self.documents.get_by_id(document_id, with_versions=True)
        assert refreshed is not None
        return refreshed

    async def process_version(
        self,
        document_id: int,
        version_id: int,
    ) -> KnowledgeDocumentVersion:
        """解析, 切分, Embedding 并写入一个知识版本.

        Args:
            document_id: 文档 ID.
            version_id: 版本 ID.

        Returns:
            状态为 INDEXED 的版本.

        Raises:
            ConflictException: 版本状态不允许处理或索引失败.
            ValidationException: 没有可提取文本.
        """
        # ① 行锁检查文档和版本状态, 并把状态置为 PROCESSING.
        async with transaction_context(self.session):
            document = await self.documents.get_by_id(
                document_id,
                for_update=True,
            )
            version = await self.versions.get_by_document_and_version(
                document_id,
                version_id,
                for_update=True,
            )
            if document is None or version is None:
                raise ResourceNotFoundException(
                    message="Knowledge version not found",
                    code="KNOWLEDGE_VERSION_NOT_FOUND",
                )
            if document.status != "ACTIVE":
                raise ConflictException(
                    message="Knowledge document is not active",
                    code="KNOWLEDGE_DOCUMENT_NOT_ACTIVE",
                )
            if version.status == "PROCESSING":
                raise ConflictException(
                    message="Knowledge version is already processing",
                    code="KNOWLEDGE_VERSION_PROCESSING",
                )
            if version.status in {"PUBLISHED", "SUPERSEDED"}:
                raise ConflictException(
                    message="Published version cannot be reprocessed",
                    code="KNOWLEDGE_VERSION_IMMUTABLE",
                )
            if version.status not in {"UPLOADED", "FAILED", "INDEXED"}:
                raise ConflictException(
                    message="Knowledge version cannot be processed",
                    code="KNOWLEDGE_VERSION_STATE_CONFLICT",
                )

            version.status = "PROCESSING"
            version.error_message = None
            await self.versions.save(version)
            storage_key = version.storage_key
            original_filename = version.original_filename

        try:
            # ② 先清理旧向量, 再解析, 清洗和切分.
            await self.vector_store.delete_by_version(version.id)
            content = await self.storage.read(storage_key)
            parsed = await asyncio.to_thread(
                self.parser.parse,
                original_filename,
                content,
            )
            cleaned = clean_documents(parsed)
            chunks = await self.chunker.chunk(cleaned)
            if not chunks:
                raise ValidationException(
                    message="Knowledge document has no extractable text",
                    code="KNOWLEDGE_NO_TEXT",
                )

            async with transaction_context(self.session):
                # ③ Chunk 正文以 MySQL 为权威源, 重复处理时先删旧行.
                while True:
                    old_chunks = await self.chunks.list_by_version(version.id)
                    if not old_chunks:
                        break
                    await self.chunks.delete_by_version(version.id)

                chunk_rows = await self.chunks.bulk_create(
                    document_id=version.document_id,
                    version_id=version.id,
                    chunks=[
                        {
                            "chunk_index": chunk.chunk_index,
                            "content": chunk.content,
                            "content_hash": hashlib.sha256(
                                chunk.content.encode("utf-8")
                            ).hexdigest(),
                            "token_count": chunk.token_count,
                            "page_number": chunk.page_number,
                            "section_title": chunk.section_title,
                            "start_offset": None,
                            "end_offset": None,
                            "chunk_metadata": chunk.chunk_metadata,
                        }
                        for chunk in chunks
                    ],
                )
                version = await self.versions.get_by_id(version.id)
                assert version is not None
                version.chunk_count = len(chunk_rows)
                version.parser_version = PARSER_VERSION
                version.chunking_version = "structural-v1"
                version.embedding_model = self.settings.rag_embedding_model
                version.embedding_dimension = self.settings.rag_embedding_dimension
                await self.versions.save(version)

            vectors = await self.embedding.embed_documents(
                [chunk.content for chunk in chunks]
            )
            # ④ 只有 MySQL Chunk 和 Qdrant 数量一致才标记 INDEXED.
            points = [
                VectorPoint(
                    chunk_id=chunk_row.id,
                    vector=vector,
                    document_id=chunk_row.document_id,
                    version_id=chunk_row.version_id,
                    embedding_model=self.settings.rag_embedding_model,
                )
                for chunk_row, vector in zip(chunk_rows, vectors, strict=True)
            ]
            await self.vector_store.upsert(points)
            indexed_count = await self.vector_store.count_by_version(version.id)

            if indexed_count != len(chunk_rows):
                raise RuntimeError("Qdrant index count does not match MySQL chunks")

            async with transaction_context(self.session):
                version = await self.versions.get_by_id(version.id)
                if version is None:
                    raise ResourceNotFoundException(
                        message="Knowledge version not found",
                        code="KNOWLEDGE_VERSION_NOT_FOUND",
                    )
                version.status = "INDEXED"
                version.error_message = None
                await self.versions.save(version)
            return version
        except Exception as exc:
            # ⑤ 任一步失败都清理向量并把版本标成 FAILED, 允许 retry.
            logger.exception("knowledge version processing failed")
            await self.session.rollback()
            try:
                await self.vector_store.delete_by_version(version_id)
            except Exception:
                logger.warning("failed to clean Qdrant vectors", exc_info=True)
            try:
                async with transaction_context(self.session):
                    failed = await self.versions.get_by_id(version_id)
                    if failed is not None:
                        failed.status = "FAILED"
                        failed.error_message = self._safe_error(exc)
                        await self.versions.save(failed)
            except Exception:
                logger.exception("failed to mark knowledge version FAILED")
            if isinstance(exc, (ValidationException, ConflictException)):
                raise
            raise ConflictException(
                message="Knowledge version processing failed",
                code="KNOWLEDGE_PROCESSING_FAILED",
            ) from exc

    async def publish_version(
        self,
        *,
        user: User,
        document_id: int,
        version_id: int,
    ) -> KnowledgeDocumentVersion:
        """发布已索引版本, 并把旧发布版本标记为 SUPERSEDED."""
        self._require_admin(user)
        async with transaction_context(self.session):
            document = await self.documents.get_by_id(
                document_id,
                for_update=True,
            )
            if document is None or document.status == "DELETED":
                raise ResourceNotFoundException(
                    message="Knowledge document not found",
                    code="KNOWLEDGE_DOCUMENT_NOT_FOUND",
                )
            if document.status != "ACTIVE":
                raise ConflictException(
                    message="Knowledge document is not active",
                    code="KNOWLEDGE_DOCUMENT_NOT_ACTIVE",
                )
            version = await self.versions.get_by_document_and_version(
                document_id,
                version_id,
                for_update=True,
            )
            if version is None:
                raise ResourceNotFoundException(
                    message="Knowledge version not found",
                    code="KNOWLEDGE_VERSION_NOT_FOUND",
                )
            if version.status != "INDEXED":
                raise ConflictException(
                    message="Only indexed versions can be published",
                    code="KNOWLEDGE_VERSION_NOT_INDEXED",
                )

            if document.current_published_version_id is not None:
                old = await self.versions.get_by_id(
                    document.current_published_version_id,
                    for_update=True,
                )
                if old is not None and old.id != version.id:
                    old.status = "SUPERSEDED"
                    await self.versions.save(old)

            version.status = "PUBLISHED"
            version.published_at = _utc_now()
            document.current_published_version_id = version.id
            document.updated_by = user.id
            await self.versions.save(version)
            await self.documents.save(document)
            return version

    async def retry_version(
        self,
        *,
        user: User,
        document_id: int,
        version_id: int,
    ) -> KnowledgeDocumentVersion:
        """只允许重试 FAILED 版本, 复用同一记录重新索引."""
        self._require_admin(user)
        version = await self.versions.get_by_document_and_version(
            document_id,
            version_id,
        )
        if version is None:
            raise ResourceNotFoundException(
                message="Knowledge version not found",
                code="KNOWLEDGE_VERSION_NOT_FOUND",
            )
        if version.status != "FAILED":
            raise ConflictException(
                message="Only failed versions can be retried",
                code="KNOWLEDGE_VERSION_NOT_RETRYABLE",
            )
        return await self.process_version(document_id, version_id)

    async def delete_document(self, *, user: User, document_id: int) -> None:
        """软删除文档, 并尽力清理 Qdrant 向量."""
        self._require_admin(user)
        async with transaction_context(self.session):
            document = await self.documents.get_by_id(
                document_id,
                for_update=True,
            )
            if document is None or document.status == "DELETED":
                raise ResourceNotFoundException(
                    message="Knowledge document not found",
                    code="KNOWLEDGE_DOCUMENT_NOT_FOUND",
                )
            document.status = "DELETED"
            document.updated_by = user.id
            await self.documents.save(document)

        try:
            await self.vector_store.delete_by_document(document_id)
        except Exception:
            # The MySQL status is authoritative; cleanup can be retried by command.
            logger.warning("Qdrant document cleanup failed", exc_info=True)

    async def list_documents(
        self,
        *,
        user: User,
        page: int,
        page_size: int,
        keyword: str | None,
        status: str | None,
        visibility: str | None,
    ) -> tuple[list[KnowledgeDocument], int]:
        """按角色过滤后分页查询知识文档."""
        is_admin = user.is_admin
        items = await self.documents.list_documents(
            is_admin=is_admin,
            status=status,
            visibility=visibility,
            keyword=keyword,
            page=page,
            page_size=page_size,
        )
        total = await self.documents.count(
            is_admin=is_admin,
            status=status,
            visibility=visibility,
            keyword=keyword,
        )
        return list(items), total

    async def get_document(
        self,
        *,
        user: User,
        document_id: int,
    ) -> KnowledgeDocument:
        """读取文档; 非管理员只能看到 ACTIVE 且 PUBLIC 的文档."""
        document = await self.documents.get_by_id(
            document_id,
            with_versions=True,
        )
        if document is None or document.status == "DELETED":
            raise ResourceNotFoundException(
                message="Knowledge document not found",
                code="KNOWLEDGE_DOCUMENT_NOT_FOUND",
            )
        if not user.is_admin and (
            document.status != "ACTIVE" or document.visibility != "PUBLIC"
        ):
            raise ResourceNotFoundException(
                message="Knowledge document not found",
                code="KNOWLEDGE_DOCUMENT_NOT_FOUND",
            )
        return document

    async def get_version(
        self,
        *,
        user: User,
        document_id: int,
        version_id: int,
    ) -> KnowledgeDocumentVersion:
        """读取指定版本, 先校验文档对当前用户可见."""
        document = await self.get_document(
            user=user,
            document_id=document_id,
        )
        version = await self.versions.get_by_document_and_version(
            document.id,
            version_id,
        )
        if version is None:
            raise ResourceNotFoundException(
                message="Knowledge version not found",
                code="KNOWLEDGE_VERSION_NOT_FOUND",
            )
        return version
