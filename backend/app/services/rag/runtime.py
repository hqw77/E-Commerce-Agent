"""RAG 运行时单例.

文件职责:
- 进程内复用 Embedding Provider, Qdrant 客户端和 Chunker.
- 避免每次请求重复加载模型或创建连接.

核心边界:
这些对象是进程级资源; 测试可显式构造独立实例覆盖.
"""

from app.core.config import Settings, get_settings
from app.infrastructure.vector.qdrant import QdrantVectorStore
from app.services.rag.chunker import Chunker
from app.services.rag.embedding import BgeM3EmbeddingProvider

# 懒加载的进程级单例.
_embedding_provider: BgeM3EmbeddingProvider | None = None
_vector_store: QdrantVectorStore | None = None
_chunker: Chunker | None = None


def get_embedding_provider(settings: Settings | None = None) -> BgeM3EmbeddingProvider:
    """返回进程级 BGE-M3 Provider."""
    global _embedding_provider
    if _embedding_provider is None:
        _embedding_provider = BgeM3EmbeddingProvider(settings or get_settings())
    return _embedding_provider


def get_vector_store(settings: Settings | None = None) -> QdrantVectorStore:
    """返回进程级 Qdrant VectorStore."""
    global _vector_store
    if _vector_store is None:
        _vector_store = QdrantVectorStore(settings or get_settings())
    return _vector_store


def get_chunker(settings: Settings | None = None) -> Chunker:
    """返回进程级 Chunker."""
    global _chunker
    if _chunker is None:
        _chunker = Chunker(settings or get_settings())
    return _chunker
