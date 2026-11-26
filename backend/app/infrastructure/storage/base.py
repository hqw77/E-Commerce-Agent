"""原始知识文档的存储接口.

文件职责:
- 抽象原始文件的保存, 读取和删除.
- 让 RAG 文档服务只依赖 storage_key, 不关心本地或对象存储实现.

核心边界:
storage_key 是不透明标识, 不能直接当作可信文件路径.
"""

from typing import Protocol


class FileStorage(Protocol):
    """知识文档原始文件存储边界."""

    async def save(self, file_content: bytes, filename: str) -> str:
        """保存字节并返回不透明 storage_key."""
        ...

    async def read(self, storage_key: str) -> bytes:
        """按 storage_key 读取原始字节."""
        ...

    async def delete(self, storage_key: str) -> None:
        """删除文件; 不存在时应保持幂等."""
        ...
