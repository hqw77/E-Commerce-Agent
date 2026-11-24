from dataclasses import dataclass
from typing import Literal

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


@dataclass(frozen=True, slots=True)
class RetrievalOutcome:
    """Retrieved items plus a coarse, non-sensitive diagnostic reason."""

    items: list[RetrievalItem]
    reason: Literal["OK", "NO_ALLOWED_DOCUMENTS", "NO_CANDIDATES"]
    allowed_document_count: int
    candidate_count: int


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
        outcome = await self.retrieve_with_diagnostics(
            user=user,
            query=query,
            top_k=top_k,
        )
        return outcome.items

    async def retrieve_with_diagnostics(
        self,
        *,
        user: User,
        query: str,
        top_k: int | None = None,
    ) -> RetrievalOutcome:
        limit = min(
            top_k or self.settings.rag_top_k,
            self.settings.rag_top_k,
        )
        allowed = await self.documents.list_retrievable_versions(
            is_admin=user.is_admin,
        )
        if not allowed:
            return RetrievalOutcome(
                items=[],
                reason="NO_ALLOWED_DOCUMENTS",
                allowed_document_count=0,
                candidate_count=0,
            )

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
            return RetrievalOutcome(
                items=[],
                reason="NO_CANDIDATES",
                allowed_document_count=len(allowed),
                candidate_count=0,
            )

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
        return RetrievalOutcome(
            items=items,
            reason="OK" if items else "NO_CANDIDATES",
            allowed_document_count=len(allowed),
            candidate_count=len(candidates),
        )
