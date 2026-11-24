"""Retrieval diagnostics tests for TASK-021.2 (no database required)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from app.core.config import Settings
from app.schemas.knowledge import RetrievalItem
from app.services.rag.retrieval_service import KnowledgeRetrievalService

pytestmark = pytest.mark.asyncio(loop_scope="module")


class FakeDocuments:
    def __init__(self, allowed: list[tuple[int, int]]) -> None:
        self.allowed = allowed

    async def list_retrievable_versions(self, *, is_admin: bool) -> list[tuple[int, int]]:
        del is_admin
        return self.allowed


class FakeChunks:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    async def list_retrieval_rows(
        self,
        *,
        chunk_ids: list[int],
        is_admin: bool,
    ) -> list[Any]:
        del chunk_ids, is_admin
        return self.rows


class FakeEmbedding:
    async def embed_query(self, query: str) -> list[float]:
        del query
        return [1.0, 0.0]


class FakeVectorStore:
    def __init__(self, candidates: list[Any]) -> None:
        self.candidates = candidates

    async def search(self, **kwargs: object) -> list[Any]:
        del kwargs
        return self.candidates


def _service(
    *,
    documents: list[tuple[int, int]],
    candidates: list[Any],
    rows: list[Any],
) -> KnowledgeRetrievalService:
    service = KnowledgeRetrievalService(
        None,  # type: ignore[arg-type]
        Settings(_env_file=None),
        embedding=FakeEmbedding(),  # type: ignore[arg-type]
        vector_store=FakeVectorStore(candidates),  # type: ignore[arg-type]
    )
    service.documents = FakeDocuments(documents)  # type: ignore[assignment]
    service.chunks = FakeChunks(rows)  # type: ignore[assignment]
    return service


async def test_no_allowed_documents_is_acl_diagnostic() -> None:
    service = _service(documents=[], candidates=[], rows=[])
    outcome = await service.retrieve_with_diagnostics(
        user=SimpleNamespace(id=1, is_admin=False),
        query="退款",
    )
    assert outcome.items == []
    assert outcome.reason == "NO_ALLOWED_DOCUMENTS"
    assert outcome.allowed_document_count == 0


async def test_no_candidates_is_retrieval_diagnostic() -> None:
    service = _service(documents=[(1, 2)], candidates=[], rows=[])
    outcome = await service.retrieve_with_diagnostics(
        user=SimpleNamespace(id=1, is_admin=False),
        query="退款",
    )
    assert outcome.items == []
    assert outcome.reason == "NO_CANDIDATES"
    assert outcome.allowed_document_count == 1


async def test_ok_outcome_preserves_retrieval_items() -> None:
    chunk = SimpleNamespace(
        id=9,
        content="退款需要审核。",
        page_number=None,
        section_title=None,
    )
    document = SimpleNamespace(id=3, title="退款规则")
    version = SimpleNamespace(id=4, original_filename="rules.md")
    candidate = SimpleNamespace(chunk_id=9, score=0.88)
    service = _service(
        documents=[(3, 4)],
        candidates=[candidate],
        rows=[(chunk, document, version)],
    )
    outcome = await service.retrieve_with_diagnostics(
        user=SimpleNamespace(id=1, is_admin=False),
        query="退款",
    )
    assert outcome.reason == "OK"
    assert outcome.candidate_count == 1
    assert outcome.items == [
        RetrievalItem(
            chunk_id=9,
            document_id=3,
            version_id=4,
            document_title="退款规则",
            content="退款需要审核。",
            score=0.88,
            page_number=None,
            section_title=None,
            original_filename="rules.md",
        )
    ]
    assert await service.retrieve(
        user=SimpleNamespace(id=1, is_admin=False),
        query="退款",
    ) == outcome.items
