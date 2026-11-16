from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_document_version import KnowledgeDocumentVersion


class KnowledgeDocumentRepository:
    """Database operations for logical knowledge documents."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        document_id: int,
        *,
        for_update: bool = False,
        with_versions: bool = False,
    ) -> KnowledgeDocument | None:
        statement = select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id
        )

        if with_versions:
            statement = statement.options(
                selectinload(KnowledgeDocument.versions)
            )
        if for_update:
            statement = statement.with_for_update()

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_title(self, title: str) -> KnowledgeDocument | None:
        result = await self.session.execute(
            select(KnowledgeDocument).where(KnowledgeDocument.title == title)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        title: str,
        description: str | None,
        visibility: str,
        created_by: int,
    ) -> KnowledgeDocument:
        document = KnowledgeDocument(
            title=title,
            description=description,
            visibility=visibility,
            status="ACTIVE",
            created_by=created_by,
            updated_by=created_by,
        )
        self.session.add(document)
        await self.session.flush()
        await self.session.refresh(document)
        return document

    async def save(self, document: KnowledgeDocument) -> KnowledgeDocument:
        await self.session.flush()
        await self.session.refresh(document)
        return document

    @staticmethod
    def _filters(
        *,
        is_admin: bool,
        status: str | None,
        visibility: str | None,
        keyword: str | None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []

        if is_admin:
            if status is not None:
                filters.append(KnowledgeDocument.status == status)
            if visibility is not None:
                filters.append(KnowledgeDocument.visibility == visibility)
        else:
            filters.append(KnowledgeDocument.status == "ACTIVE")
            filters.append(KnowledgeDocument.visibility == "PUBLIC")

        if keyword:
            filters.append(KnowledgeDocument.title.like(f"%{keyword}%"))

        return filters

    async def count(
        self,
        *,
        is_admin: bool,
        status: str | None,
        visibility: str | None,
        keyword: str | None,
    ) -> int:
        statement = select(func.count(KnowledgeDocument.id)).where(
            *self._filters(
                is_admin=is_admin,
                status=status,
                visibility=visibility,
                keyword=keyword,
            )
        )
        result = await self.session.execute(statement)
        return int(result.scalar_one())

    async def list_documents(
        self,
        *,
        is_admin: bool,
        status: str | None,
        visibility: str | None,
        keyword: str | None,
        page: int,
        page_size: int,
    ) -> Sequence[KnowledgeDocument]:
        statement = (
            select(KnowledgeDocument)
            .where(
                *self._filters(
                    is_admin=is_admin,
                    status=status,
                    visibility=visibility,
                    keyword=keyword,
                )
            )
            .order_by(KnowledgeDocument.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def list_retrievable_versions(
        self,
        *,
        is_admin: bool,
    ) -> Sequence[tuple[int, int]]:
        """Return (document_id, published_version_id) pairs allowed for a user."""
        filters = [
            KnowledgeDocument.status == "ACTIVE",
            KnowledgeDocument.current_published_version_id.is_not(None),
            KnowledgeDocumentVersion.status == "PUBLISHED",
            KnowledgeDocumentVersion.id
            == KnowledgeDocument.current_published_version_id,
        ]

        if not is_admin:
            filters.append(KnowledgeDocument.visibility == "PUBLIC")

        statement = (
            select(
                KnowledgeDocument.id,
                KnowledgeDocumentVersion.id,
            )
            .join(
                KnowledgeDocumentVersion,
                KnowledgeDocumentVersion.id
                == KnowledgeDocument.current_published_version_id,
            )
            .where(*filters)
            .order_by(KnowledgeDocument.id)
        )
        result = await self.session.execute(statement)
        return [(int(row[0]), int(row[1])) for row in result.all()]


class KnowledgeVersionRepository:
    """Database operations for document versions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        version_id: int,
        *,
        for_update: bool = False,
    ) -> KnowledgeDocumentVersion | None:
        statement = select(KnowledgeDocumentVersion).where(
            KnowledgeDocumentVersion.id == version_id
        )

        if for_update:
            statement = statement.with_for_update()

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_document_and_version(
        self,
        document_id: int,
        version_id: int,
        *,
        for_update: bool = False,
    ) -> KnowledgeDocumentVersion | None:
        statement = select(KnowledgeDocumentVersion).where(
            KnowledgeDocumentVersion.document_id == document_id,
            KnowledgeDocumentVersion.id == version_id,
        )

        if for_update:
            statement = statement.with_for_update()

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_by_document(
        self,
        document_id: int,
    ) -> Sequence[KnowledgeDocumentVersion]:
        result = await self.session.execute(
            select(KnowledgeDocumentVersion)
            .where(KnowledgeDocumentVersion.document_id == document_id)
            .order_by(KnowledgeDocumentVersion.version_no.desc())
        )
        return list(result.scalars().all())

    async def get_next_version_no(self, document_id: int) -> int:
        result = await self.session.execute(
            select(func.max(KnowledgeDocumentVersion.version_no)).where(
                KnowledgeDocumentVersion.document_id == document_id
            )
        )
        current = result.scalar_one_or_none()
        return int(current or 0) + 1

    async def create(
        self,
        *,
        document_id: int,
        version_no: int,
        original_filename: str,
        storage_key: str,
        mime_type: str,
        file_size: int,
        file_sha256: str,
    ) -> KnowledgeDocumentVersion:
        version = KnowledgeDocumentVersion(
            document_id=document_id,
            version_no=version_no,
            original_filename=original_filename,
            storage_key=storage_key,
            mime_type=mime_type,
            file_size=file_size,
            file_sha256=file_sha256,
            status="UPLOADED",
            chunk_count=0,
        )
        self.session.add(version)
        await self.session.flush()
        await self.session.refresh(version)
        return version

    async def save(
        self,
        version: KnowledgeDocumentVersion,
    ) -> KnowledgeDocumentVersion:
        await self.session.flush()
        await self.session.refresh(version)
        return version


class KnowledgeChunkRepository:
    """Database operations for authoritative chunk text."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_version(
        self,
        version_id: int,
    ) -> Sequence[KnowledgeChunk]:
        result = await self.session.execute(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.version_id == version_id)
            .order_by(KnowledgeChunk.chunk_index)
        )
        return list(result.scalars().all())

    async def count_by_version(self, version_id: int) -> int:
        result = await self.session.execute(
            select(func.count(KnowledgeChunk.id)).where(
                KnowledgeChunk.version_id == version_id
            )
        )
        return int(result.scalar_one())

    async def delete_by_version(self, version_id: int) -> None:
        chunks = await self.list_by_version(version_id)
        for chunk in chunks:
            await self.session.delete(chunk)
        await self.session.flush()

    async def bulk_create(
        self,
        *,
        document_id: int,
        version_id: int,
        chunks: Sequence[dict[str, object]],
    ) -> list[KnowledgeChunk]:
        models = [
            KnowledgeChunk(
                document_id=document_id,
                version_id=version_id,
                chunk_index=chunk["chunk_index"],
                content=chunk["content"],
                content_hash=chunk["content_hash"],
                token_count=chunk["token_count"],
                page_number=chunk.get("page_number"),
                section_title=chunk.get("section_title"),
                start_offset=chunk.get("start_offset"),
                end_offset=chunk.get("end_offset"),
                chunk_metadata=chunk.get("chunk_metadata"),
            )
            for chunk in chunks
        ]
        self.session.add_all(models)
        await self.session.flush()
        return models

    async def list_retrieval_rows(
        self,
        *,
        chunk_ids: Sequence[int],
        is_admin: bool,
    ) -> Sequence[tuple[KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentVersion]]:
        """MySQL authority check and text fetch for Qdrant-returned chunk IDs."""
        if not chunk_ids:
            return []

        filters = [
            KnowledgeChunk.id.in_(chunk_ids),
            KnowledgeDocument.status == "ACTIVE",
            KnowledgeDocumentVersion.status == "PUBLISHED",
            KnowledgeDocument.current_published_version_id
            == KnowledgeDocumentVersion.id,
        ]

        if not is_admin:
            filters.append(KnowledgeDocument.visibility == "PUBLIC")

        statement = (
            select(
                KnowledgeChunk,
                KnowledgeDocument,
                KnowledgeDocumentVersion,
            )
            .join(
                KnowledgeDocument,
                KnowledgeDocument.id == KnowledgeChunk.document_id,
            )
            .join(
                KnowledgeDocumentVersion,
                KnowledgeDocumentVersion.id == KnowledgeChunk.version_id,
            )
            .where(*filters)
            .order_by(KnowledgeChunk.id)
        )
        result = await self.session.execute(statement)
        return [
            (row[0], row[1], row[2])
            for row in result.all()
        ]
