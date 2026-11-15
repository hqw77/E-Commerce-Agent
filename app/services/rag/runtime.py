from app.core.config import Settings, get_settings
from app.infrastructure.vector.qdrant import QdrantVectorStore
from app.services.rag.chunker import Chunker
from app.services.rag.embedding import BgeM3EmbeddingProvider

_embedding_provider: BgeM3EmbeddingProvider | None = None
_vector_store: QdrantVectorStore | None = None
_chunker: Chunker | None = None


def get_embedding_provider(settings: Settings | None = None) -> BgeM3EmbeddingProvider:
    global _embedding_provider
    if _embedding_provider is None:
        _embedding_provider = BgeM3EmbeddingProvider(settings or get_settings())
    return _embedding_provider


def get_vector_store(settings: Settings | None = None) -> QdrantVectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = QdrantVectorStore(settings or get_settings())
    return _vector_store


def get_chunker(settings: Settings | None = None) -> Chunker:
    global _chunker
    if _chunker is None:
        _chunker = Chunker(settings or get_settings())
    return _chunker
