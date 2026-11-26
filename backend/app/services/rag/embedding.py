"""BGE-M3 Embedding 提供器.

文件职责:
- 延迟加载本地 BGE-M3 模型.
- 批量生成归一化的 1024 维向量.
- 校验向量数量, 维度和有限值.

核心边界:
模型加载放在线程中, 避免阻塞事件循环; 失败统一映射为 503.
"""

import asyncio
import math
import os
from pathlib import Path
from typing import Any

from sentence_transformers import SentenceTransformer

from app.core.config import Settings
from app.core.exceptions import AppException


class BgeM3EmbeddingProvider:
    """延迟加载的 BGE-M3 本地 Embedding 提供器."""

    def __init__(self, settings: Settings) -> None:
        """保存配置并初始化模型加载锁."""
        self.settings = settings
        self._model: Any | None = None
        self._load_lock = asyncio.Lock()

    async def _get_model(self) -> Any:
        """首次调用时加载模型, 并发请求只加载一次."""
        if self._model is not None:
            return self._model

        async with self._load_lock:
            # ① 双重检查, 防止等待锁期间其他协程已经加载完成.
            if self._model is not None:
                return self._model

            try:
                # ② 固定 HuggingFace 缓存目录, 避免模型文件散落.
                cache_dir = str(
                    Path(self.settings.rag_embedding_cache_dir).resolve()
                )
                os.environ.setdefault("HF_HOME", cache_dir)
                os.environ.setdefault(
                    "HUGGINGFACE_HUB_CACHE",
                    str(Path(cache_dir) / "hub"),
                )
                os.environ.setdefault(
                    "HF_XET_CACHE",
                    str(Path(cache_dir) / "xet"),
                )
                os.environ["HF_HUB_DISABLE_XET"] = "1"
                # ③ SentenceTransformer 是同步阻塞的, 放到线程中执行.
                self._model = await asyncio.to_thread(
                    SentenceTransformer,
                    self.settings.rag_embedding_model,
                    device=self.settings.rag_embedding_device,
                    cache_folder=cache_dir,
                )
            except Exception as exc:
                raise AppException(
                    message="BGE-M3 embedding model is unavailable",
                    code="RAG_EMBEDDING_UNAVAILABLE",
                    status_code=503,
                ) from exc

            return self._model

    def _validate(self, vectors: list[list[float]], expected: int) -> None:
        """校验向量数量, 维度和所有值都是有限数."""
        if len(vectors) != expected:
            raise AppException(
                message="Embedding result count mismatch",
                code="RAG_EMBEDDING_INVALID",
                status_code=503,
            )

        for vector in vectors:
            if len(vector) != self.settings.rag_embedding_dimension:
                raise AppException(
                    message="Embedding dimension mismatch",
                    code="RAG_EMBEDDING_INVALID",
                    status_code=503,
                )
            if any(not math.isfinite(value) for value in vector):
                raise AppException(
                    message="Embedding contains non-finite values",
                    code="RAG_EMBEDDING_INVALID",
                    status_code=503,
                )

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量生成文档向量.

        Args:
            texts: 待向量化文本.

        Returns:
            与输入数量一致的归一化向量列表.
        """
        if not texts:
            return []

        model = await self._get_model()
        try:
            encoded = await asyncio.to_thread(
                model.encode,
                texts,
                batch_size=self.settings.rag_embedding_batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
        except Exception as exc:
            raise AppException(
                message="Embedding generation failed",
                code="RAG_EMBEDDING_FAILED",
                status_code=503,
            ) from exc

        vectors = [[float(value) for value in row] for row in encoded.tolist()]
        self._validate(vectors, len(texts))
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        """生成单条 query 向量."""
        vectors = await self.embed_documents([text])
        return vectors[0]
