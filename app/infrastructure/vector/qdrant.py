from dataclasses import dataclass
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from app.core.config import Settings


@dataclass(frozen=True)
class VectorPoint:
    chunk_id: int
    vector: list[float]
    document_id: int
    version_id: int
    embedding_model: str


@dataclass(frozen=True)
class VectorSearchResult:
    chunk_id: int
    score: float
    document_id: int
    version_id: int


class QdrantVectorStore:
    """Qdrant-only vector storage; chunk text remains in MySQL."""

    def __init__(self, settings: Settings) -> None:
        self.collection = settings.rag_collection
        self.embedding_model = settings.rag_embedding_model
        self.dimension = settings.rag_embedding_dimension
        self.client = AsyncQdrantClient(
            url=settings.rag_qdrant_url,
            api_key=settings.rag_qdrant_api_key.get_secret_value() or None,
            timeout=30,
        )

    async def ensure_collection(self) -> None:
        exists = await self.client.collection_exists(self.collection)
        if not exists:
            await self.client.create_collection(
                collection_name=self.collection,
                vectors_config=models.VectorParams(
                    size=self.dimension,
                    distance=models.Distance.COSINE,
                ),
            )
        info = await self.client.get_collection(self.collection)
        vectors = info.config.params.vectors
        if isinstance(vectors, models.VectorParams):
            if vectors.size != self.dimension:
                raise RuntimeError("Qdrant collection vector dimension mismatch")
            if vectors.distance != models.Distance.COSINE:
                raise RuntimeError("Qdrant collection distance must be COSINE")

        schema = await self.client.get_collection(self.collection)
        payload_schema = schema.payload_schema
        for field_name, field_type in (
            ("document_id", models.PayloadSchemaType.INTEGER),
            ("version_id", models.PayloadSchemaType.INTEGER),
            ("embedding_model", models.PayloadSchemaType.KEYWORD),
        ):
            if field_name not in payload_schema:
                await self.client.create_payload_index(
                    collection_name=self.collection,
                    field_name=field_name,
                    field_schema=field_type,
                    wait=True,
                )

    async def upsert(self, points: list[VectorPoint]) -> None:
        if not points:
            return
        await self.ensure_collection()
        await self.client.upsert(
            collection_name=self.collection,
            points=[
                models.PointStruct(
                    id=point.chunk_id,
                    vector=point.vector,
                    payload={
                        "chunk_id": point.chunk_id,
                        "document_id": point.document_id,
                        "version_id": point.version_id,
                        "embedding_model": point.embedding_model,
                    },
                )
                for point in points
            ],
            wait=True,
        )

    async def search(
        self,
        *,
        query_vector: list[float],
        version_ids: list[int],
        limit: int,
    ) -> list[VectorSearchResult]:
        if not version_ids:
            return []

        await self.ensure_collection()
        response = await self.client.query_points(
            collection_name=self.collection,
            query=query_vector,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="version_id",
                        match=models.MatchAny(any=version_ids),
                    ),
                    models.FieldCondition(
                        key="embedding_model",
                        match=models.MatchValue(value=self.embedding_model),
                    ),
                ]
            ),
            limit=limit,
            with_payload=True,
        )

        results: list[VectorSearchResult] = []
        for point in response.points:
            payload: dict[str, Any] = point.payload or {}
            results.append(
                VectorSearchResult(
                    chunk_id=int(point.id),
                    score=float(point.score),
                    document_id=int(payload["document_id"]),
                    version_id=int(payload["version_id"]),
                )
            )
        return results

    async def count_by_version(self, version_id: int) -> int:
        await self.ensure_collection()
        result = await self.client.count(
            collection_name=self.collection,
            count_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="version_id",
                        match=models.MatchValue(value=version_id),
                    ),
                    models.FieldCondition(
                        key="embedding_model",
                        match=models.MatchValue(value=self.embedding_model),
                    ),
                ]
            ),
            exact=True,
        )
        return int(result.count)

    async def delete_by_version(self, version_id: int) -> None:
        await self.ensure_collection()
        await self.client.delete(
            collection_name=self.collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="version_id",
                            match=models.MatchValue(value=version_id),
                        )
                    ]
                )
            ),
            wait=True,
        )

    async def delete_by_document(self, document_id: int) -> None:
        await self.ensure_collection()
        await self.client.delete(
            collection_name=self.collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=document_id),
                        )
                    ]
                )
            ),
            wait=True,
        )

    async def health_check(self) -> bool:
        try:
            await self.client.get_collections()
            return True
        except Exception:  # noqa: BLE001 - health check must not expose client details
            return False

    async def close(self) -> None:
        await self.client.close()
