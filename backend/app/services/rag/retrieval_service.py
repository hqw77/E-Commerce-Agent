from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import AppException
from app.infrastructure.vector.qdrant import QdrantVectorStore
from app.models.user import User
from app.repositories.knowledge import (
    KnowledgeChunkRepository,
    KnowledgeDocumentRepository,
)
from app.schemas.knowledge import RetrievalItem
from app.services.rag.embedding import BgeM3EmbeddingProvider


class KnowledgeRetrievalService:
    """Dense retrieval with pre-filtering and authoritative MySQL validation."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings | None = None,
        *,
        embedding: BgeM3EmbeddingProvider | None = None,
        vector_store: QdrantVectorStore | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.embedding = embedding or BgeM3EmbeddingProvider(self.settings)
        self.vector_store = vector_store or QdrantVectorStore(self.settings)
        self.documents = KnowledgeDocumentRepository(session)
        self.chunks = KnowledgeChunkRepository(session)

    async def retrieve(
        self,
        *,
        user: User,
        query: str,
        top_k: int | None = None,
    ) -> list[RetrievalItem]:
        limit = min(
            top_k or self.settings.rag_top_k,
            self.settings.rag_top_k,
        )
        allowed = await self.documents.list_retrievable_versions(
            is_admin=user.is_admin,
        )
        if not allowed:
            return []

        version_ids = [version_id for _document_id, version_id in allowed]
        try:
            query_vector = await self.embedding.embed_query(query)
            candidates = await self.vector_store.search(
                query_vector=query_vector,
                version_ids=version_ids,
                limit=min(
                    max(limit, self.settings.rag_max_candidates),
                    self.settings.rag_max_candidates,
                ),
            )
        except AppException:
            raise
        except Exception as exc:
            raise AppException(
                message="Knowledge retrieval service is unavailable",
                code="RAG_RETRIEVAL_UNAVAILABLE",
                status_code=503,
            ) from exc

        if not candidates:
            return []

        chunk_ids = [candidate.chunk_id for candidate in candidates]
        rows = await self.chunks.list_retrieval_rows(
            chunk_ids=chunk_ids,
            is_admin=user.is_admin,
        )
        by_chunk_id = {
            chunk.id: (chunk, document, version)
            for chunk, document, version in rows
        }

        items: list[RetrievalItem] = []
        for candidate in candidates:
            row = by_chunk_id.get(candidate.chunk_id)
            if row is None:
                # Qdrant may be stale; MySQL is authoritative.
                continue
            chunk, document, version = row
            items.append(
                RetrievalItem(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    version_id=version.id,
                    document_title=document.title,
                    content=chunk.content,
                    score=float(candidate.score),
                    page_number=chunk.page_number,
                    section_title=chunk.section_title,
                    original_filename=version.original_filename,
                )
            )
            if len(items) >= limit:
                break
        return items
