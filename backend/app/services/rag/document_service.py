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
    return datetime.now(UTC).replace(tzinfo=None)


class KnowledgeDocumentService:
    """Document/version lifecycle and processing orchestration."""

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
        if not user.is_admin:
            raise PermissionDeniedException(
                message="Administrator privileges are required",
            )

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        return f"Knowledge processing failed ({type(exc).__name__})"

    async def _load_file(self, filename: str, content: bytes) -> tuple[bytes, str]:
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

        content, file_sha256 = await self._load_file(original_filename, content)
        storage_key = await self.storage.save(content, original_filename)
        mime_type = self.parser.mime_type_for(original_filename)

        try:
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
        """Process one version; status and DB rows make retries deterministic."""
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
