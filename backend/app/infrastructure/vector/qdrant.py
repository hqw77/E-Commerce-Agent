"""Qdrant 向量存储适配器.

文件职责:
- 确保 Collection 和 payload index 存在.
- 写入, 检索和删除 Chunk 向量.
- 只保存向量和轻量元数据, 不保存 Chunk 正文.

核心边界:
Qdrant 是召回层, 不是权限和正文的权威源.
"""

from dataclasses import dataclass
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from app.core.config import Settings


@dataclass(frozen=True)
class VectorPoint:
    """一个待写入 Qdrant 的向量点.

    Args:
        chunk_id: MySQL Chunk ID, 同时作为 Qdrant point ID.
        vector: 归一化后的向量.
        document_id: 所属文档 ID.
        version_id: 所属版本 ID, 检索时用于 ACL 过滤.
        embedding_model: 生成该向量的模型名.
    """

    chunk_id: int
    vector: list[float]
    document_id: int
    version_id: int
    embedding_model: str


@dataclass(frozen=True)
class VectorSearchResult:
    """Qdrant 返回的一个相似度命中.

    Args:
        chunk_id: 命中的 MySQL Chunk ID.
        score: 余弦相似度.
        document_id: payload 中的文档 ID.
        version_id: payload 中的版本 ID.
    """

    chunk_id: int
    score: float
    document_id: int
    version_id: int


class QdrantVectorStore:
    """只负责 Qdrant 向量读写的适配器."""

    def __init__(self, settings: Settings) -> None:
        """创建异步 Qdrant 客户端并缓存 Collection 配置."""
        self.collection = settings.rag_collection
        self.embedding_model = settings.rag_embedding_model
        self.dimension = settings.rag_embedding_dimension
        self.client = AsyncQdrantClient(
            url=settings.rag_qdrant_url,
            api_key=settings.rag_qdrant_api_key.get_secret_value() or None,
            timeout=30,
        )

    async def ensure_collection(self) -> None:
        """确保 Collection 维度和 payload index 与当前配置一致."""
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
        """批量写入或覆盖向量点."""
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
        """在允许的版本 ID 内做余弦相似度检索.

        Args:
            query_vector: 用户问题向量.
            version_ids: MySQL 已授权的版本 ID.
            limit: 最大返回数.

        Returns:
            按分数排序的命中列表.
        """
        if not version_ids:
            return []

        await self.ensure_collection()
        # ① 在 Qdrant 侧同时过滤版本和 embedding 模型, 避免跨模型混检.
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
        """统计某个版本在当前 embedding 模型下的向量数量."""
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
        """删除某个版本的所有向量点."""
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
        """删除某个文档所有版本的向量点."""
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
        """检查 Qdrant 是否可访问; 失败时不泄露客户端细节."""
        try:
            await self.client.get_collections()
            return True
        except Exception:  # noqa: BLE001 - health check must not expose client details
            return False

    async def close(self) -> None:
        """关闭底层 Qdrant 客户端连接."""
        await self.client.close()
