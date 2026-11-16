import asyncio
import math
import os
from pathlib import Path
from typing import Any

from sentence_transformers import SentenceTransformer

from app.core.config import Settings
from app.core.exceptions import AppException


class BgeM3EmbeddingProvider:
    """Lazy local BAAI/bge-m3 provider with validated 1024-d dense vectors."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model: Any | None = None
        self._load_lock = asyncio.Lock()

    async def _get_model(self) -> Any:
        if self._model is not None:
            return self._model

        async with self._load_lock:
            if self._model is not None:
                return self._model

            try:
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
        vectors = await self.embed_documents([text])
        return vectors[0]
