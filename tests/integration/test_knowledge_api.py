from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.api.v1 import knowledge as knowledge_api
from app.core.config import Settings
from app.db.session import AsyncSessionLocal, get_db
from app.infrastructure.vector.qdrant import VectorPoint, VectorSearchResult
from app.main import app
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_document_version import KnowledgeDocumentVersion
from app.models.user import User
from app.services.rag.chunker import Chunker, WhitespaceTokenCounter

ADMIN = SimpleNamespace(
    id=1,
    email="knowledge-admin@example.com",
    is_active=True,
    is_admin=True,
)
REGULAR = SimpleNamespace(
    id=2,
    email="knowledge-user@example.com",
    is_active=True,
    is_admin=False,
)

TITLE_PREFIX = "it-knowledge-"


class FakeEmbedding:
    fail = False

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.fail:
            from app.core.exceptions import AppException

            raise AppException(
                message="forced embedding failure",
                code="TEST_EMBEDDING_FAILURE",
                status_code=503,
            )
        return [[1.0, *([0.0] * 1023)] for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        return [1.0, *([0.0] * 1023)]


class FakeVectorStore:
    def __init__(self) -> None:
        self.points: dict[int, tuple[int, int]] = {}
        self.stale_ids: list[int] = []

    async def ensure_collection(self) -> None:
        return None

    async def upsert(self, points: list[VectorPoint]) -> None:
        for point in points:
            self.points[point.chunk_id] = (point.version_id, point.document_id)

    async def search(
        self,
        *,
        query_vector: list[float],
        version_ids: list[int],
        limit: int,
    ) -> list[VectorSearchResult]:
        matches = [
            (chunk_id, version_id, document_id)
            for chunk_id, (version_id, document_id) in self.points.items()
            if version_id in version_ids
        ]
        results = [
            VectorSearchResult(
                chunk_id=chunk_id,
                score=1.0 - index * 0.01,
                document_id=document_id,
                version_id=version_id,
            )
            for index, (chunk_id, version_id, document_id) in enumerate(matches)
        ]
        results.extend(
            VectorSearchResult(
                chunk_id=chunk_id,
                score=0.99,
                document_id=0,
                version_id=version_ids[0] if version_ids else 0,
            )
            for chunk_id in self.stale_ids
        )
        return results[:limit]

    async def count_by_version(self, version_id: int) -> int:
        return sum(1 for version, _document in self.points.values() if version == version_id)

    async def delete_by_version(self, version_id: int) -> None:
        for chunk_id, (version, _document) in list(self.points.items()):
            if version == version_id:
                del self.points[chunk_id]

    async def delete_by_document(self, document_id: int) -> None:
        for chunk_id, (_version, document) in list(self.points.items()):
            if document == document_id:
                del self.points[chunk_id]

    async def health_check(self) -> bool:
        return True

    async def close(self) -> None:
        return None


def install_user(user: SimpleNamespace) -> None:
    async def fake_current_user(
        session: Annotated[AsyncSession, Depends(get_db)],
    ) -> SimpleNamespace:
        await session.execute(text("SELECT 1"))
        return user

    app.dependency_overrides[get_current_user] = fake_current_user


@pytest_asyncio.fixture
async def api_client(
    tmp_path: Path,
) -> AsyncIterator[
    tuple[AsyncClient, FakeVectorStore, Settings, SimpleNamespace, SimpleNamespace]
]:
    async with AsyncSessionLocal() as session:
        admin = User(
            email=f"{TITLE_PREFIX}admin-{uuid4().hex[:8]}@example.com",
            password_hash="x",
            is_active=True,
            is_admin=True,
        )
        regular = User(
            email=f"{TITLE_PREFIX}user-{uuid4().hex[:8]}@example.com",
            password_hash="x",
            is_active=True,
            is_admin=False,
        )
        session.add_all([admin, regular])
        await session.commit()
        await session.refresh(admin)
        await session.refresh(regular)
        admin_user = SimpleNamespace(
            id=admin.id,
            email=admin.email,
            is_active=True,
            is_admin=True,
        )
        regular_user = SimpleNamespace(
            id=regular.id,
            email=regular.email,
            is_active=True,
            is_admin=False,
        )

    settings = Settings(
        _env_file=None,
        app_env="testing",
        rag_storage_dir=str(tmp_path),
        rag_embedding_cache_dir=str(tmp_path / "cache"),
    )
    vector_store = FakeVectorStore()

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with AsyncSessionLocal() as session:
            yield session

    original_get_settings = knowledge_api.get_settings
    original_embedding = knowledge_api.get_embedding_provider
    original_chunker = knowledge_api.get_chunker
    original_vector = knowledge_api.get_vector_store

    app.dependency_overrides[get_db] = override_get_db
    install_user(admin_user)
    knowledge_api.get_settings = lambda: settings
    knowledge_api.get_embedding_provider = lambda _settings=None: FakeEmbedding()
    knowledge_api.get_chunker = lambda _settings=None: Chunker(
        settings,
        WhitespaceTokenCounter(),
    )
    knowledge_api.get_vector_store = lambda _settings=None: vector_store

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            yield (
                client,
                vector_store,
                settings,
                admin_user,
                regular_user,
            )
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        knowledge_api.get_settings = original_get_settings
        knowledge_api.get_embedding_provider = original_embedding
        knowledge_api.get_chunker = original_chunker
        knowledge_api.get_vector_store = original_vector

        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(KnowledgeChunk).where(
                    KnowledgeChunk.document_id.in_(
                        select(KnowledgeDocument.id).where(
                            KnowledgeDocument.title.like(f"{TITLE_PREFIX}%")
                        )
                    )
                )
            )
            await session.execute(
                delete(KnowledgeDocumentVersion).where(
                    KnowledgeDocumentVersion.document_id.in_(
                        select(KnowledgeDocument.id).where(
                            KnowledgeDocument.title.like(f"{TITLE_PREFIX}%")
                        )
                    )
                )
            )
            await session.execute(
                delete(KnowledgeDocument).where(
                    KnowledgeDocument.title.like(f"{TITLE_PREFIX}%")
                )
            )
            await session.execute(
                delete(User).where(User.email.like(f"{TITLE_PREFIX}%"))
            )
            await session.commit()

        for path in tmp_path.iterdir():  # type: ignore[union-attr]
            if path.is_file():
                path.unlink()


async def upload(
    client: AsyncClient,
    *,
    title: str,
    content: bytes,
    visibility: str = "PUBLIC",
) -> dict:
    response = await client.post(
        "/api/v1/knowledge/documents",
        data={
            "title": title,
            "description": "integration test",
            "visibility": visibility,
        },
        files={"file": ("rules.md", content, "text/markdown")},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_knowledge_upload_permission_version_delete(
    api_client: tuple[
        AsyncClient,
        FakeVectorStore,
        Settings,
        SimpleNamespace,
        SimpleNamespace,
    ],
) -> None:
    client, vector_store, _settings, admin_user, regular_user = api_client
    title = f"{TITLE_PREFIX}{uuid4().hex[:8]}"
    content = "# 售后规则\n\n签收后 7 天内可以退货退款。".encode()

    first = await upload(client, title=title, content=content)
    document_id = first["id"]
    first_version = first["versions"][0]
    assert first_version["status"] == "INDEXED"
    assert first_version["chunk_count"] > 0

    publish = await client.post(
        f"/api/v1/knowledge/documents/{document_id}/versions/"
        f"{first_version['id']}/publish"
    )
    assert publish.status_code == 200, publish.text
    assert publish.json()["status"] == "PUBLISHED"

    retrieval = await client.post(
        "/api/v1/knowledge/retrieve",
        json={"query": "签收后多久可以退货？", "top_k": 3},
    )
    assert retrieval.status_code == 200, retrieval.text
    assert retrieval.json()["total"] == 1
    assert retrieval.json()["items"][0]["document_id"] == document_id

    # A normal user can see the PUBLIC document and retrieve it.
    install_user(regular_user)
    public_list = await client.get("/api/v1/knowledge/documents")
    assert public_list.status_code == 200
    assert any(item["id"] == document_id for item in public_list.json()["items"])

    # A normal user cannot upload.
    forbidden = await client.post(
        "/api/v1/knowledge/documents",
        data={"title": f"{title}-forbidden", "visibility": "PUBLIC"},
        files={"file": ("rules.md", b"test", "text/markdown")},
    )
    assert forbidden.status_code == 403

    # ADMIN_ONLY is not visible to a normal user.
    install_user(admin_user)
    admin_only = await upload(
        client,
        title=f"{title}-admin",
        content=b"# Admin\n\nInternal rule.",
        visibility="ADMIN_ONLY",
    )
    admin_only_id = admin_only["id"]
    admin_version = admin_only["versions"][0]
    admin_publish = await client.post(
        f"/api/v1/knowledge/documents/{admin_only_id}/versions/"
        f"{admin_version['id']}/publish"
    )
    assert admin_publish.status_code == 200, admin_publish.text

    install_user(regular_user)
    forbidden_detail = await client.get(
        f"/api/v1/knowledge/documents/{admin_only_id}"
    )
    assert forbidden_detail.status_code == 404
    regular_retrieval = await client.post(
        "/api/v1/knowledge/retrieve",
        json={"query": "internal", "top_k": 5},
    )
    assert regular_retrieval.status_code == 200
    assert all(
        item["document_id"] != admin_only_id
        for item in regular_retrieval.json()["items"]
    )

    # New version remains old-version-invisible until published.
    install_user(admin_user)
    new_version = await client.post(
        f"/api/v1/knowledge/documents/{document_id}/versions",
        files={
            "file": (
                "rules-v2.md",
                "# 售后规则\n\n新版规则：签收后 15 天内可以退货退款。".encode(),
                "text/markdown",
            )
        },
    )
    assert new_version.status_code == 201, new_version.text
    second_version = next(
        version
        for version in new_version.json()["versions"]
        if version["version_no"] == 2
    )
    assert second_version["version_no"] == 2
    assert second_version["status"] == "INDEXED"

    old_retrieval = await client.post(
        "/api/v1/knowledge/retrieve",
        json={"query": "多久可以退货", "top_k": 5},
    )
    assert old_retrieval.status_code == 200
    assert all(
        item["version_id"] != second_version["id"]
        for item in old_retrieval.json()["items"]
    )

    second_publish = await client.post(
        f"/api/v1/knowledge/documents/{document_id}/versions/"
        f"{second_version['id']}/publish"
    )
    assert second_publish.status_code == 200, second_publish.text
    new_retrieval = await client.post(
        "/api/v1/knowledge/retrieve",
        json={"query": "新版规则", "top_k": 5},
    )
    assert new_retrieval.status_code == 200
    assert any(
        item["version_id"] == second_version["id"]
        for item in new_retrieval.json()["items"]
    )
    assert all(
        item["version_id"] != first_version["id"]
        for item in new_retrieval.json()["items"]
    )

    # Stale Qdrant point is discarded by MySQL validation.
    vector_store.stale_ids.append(99999999)
    stale_retrieval = await client.post(
        "/api/v1/knowledge/retrieve",
        json={"query": "stale", "top_k": 5},
    )
    assert stale_retrieval.status_code == 200
    assert all(
        item["chunk_id"] != 99999999 for item in stale_retrieval.json()["items"]
    )
    vector_store.stale_ids.clear()

    # Delete exits the retrieval scope immediately.
    deleted = await client.delete(
        f"/api/v1/knowledge/documents/{document_id}"
    )
    assert deleted.status_code == 204, deleted.text
    after_delete = await client.post(
        "/api/v1/knowledge/retrieve",
        json={"query": "退货", "top_k": 5},
    )
    assert after_delete.status_code == 200
    assert all(
        item["document_id"] != document_id
        for item in after_delete.json()["items"]
    )
    assert (
        await client.get(f"/api/v1/knowledge/documents/{document_id}")
    ).status_code == 404


@pytest.mark.asyncio
async def test_failed_version_can_be_retried(
    api_client: tuple[
        AsyncClient,
        FakeVectorStore,
        Settings,
        SimpleNamespace,
        SimpleNamespace,
    ],
) -> None:
    client, _vector_store, _settings, admin_user, _regular_user = api_client
    title = f"{TITLE_PREFIX}retry-{uuid4().hex[:8]}"
    FakeEmbedding.fail = True
    try:
        response = await client.post(
            "/api/v1/knowledge/documents",
            data={"title": title, "visibility": "PUBLIC"},
            files={"file": ("rules.md", b"# Retry\n\nretry content", "text/markdown")},
        )
        assert response.status_code == 409, response.text

        documents = await client.get("/api/v1/knowledge/documents")
        assert documents.status_code == 200, documents.text
        document = next(
            item for item in documents.json()["items"] if item["title"] == title
        )
        detail = await client.get(
            f"/api/v1/knowledge/documents/{document['id']}"
        )
        assert detail.status_code == 200, detail.text
        failed = detail.json()["versions"][0]
        assert failed["status"] == "FAILED"

        FakeEmbedding.fail = False
        retried = await client.post(
            f"/api/v1/knowledge/documents/{document['id']}/versions/"
            f"{failed['id']}/retry"
        )
        assert retried.status_code == 200, retried.text
        assert retried.json()["status"] == "INDEXED"

        published = await client.post(
            f"/api/v1/knowledge/documents/{document['id']}/versions/"
            f"{failed['id']}/publish"
        )
        assert published.status_code == 200, published.text
    finally:
        FakeEmbedding.fail = False
        install_user(admin_user)
