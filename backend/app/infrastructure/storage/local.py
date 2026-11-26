"""本地文件系统存储实现.

文件职责:
- 把上传文件保存到配置的 rag_storage_dir.
- 用随机 storage_key 防止文件名冲突和路径穿越.
- 通过 asyncio.to_thread 执行阻塞文件 IO.

核心边界:
只保存原始文件; Chunk 正文仍以 MySQL 为权威源.
"""

import asyncio
from pathlib import Path
from uuid import uuid4

from app.core.config import Settings
from app.core.exceptions import ResourceNotFoundException


class LocalFileStorage:
    """FileStorage 的本地文件系统实现."""

    def __init__(self, settings: Settings) -> None:
        """解析根目录并确保它存在."""
        self.root = Path(settings.rag_storage_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, storage_key: str) -> Path:
        """把 storage_key 解析到根目录下, 防止 ../ 路径穿越."""
        candidate = (self.root / storage_key).resolve()
        if candidate.parent != self.root:
            raise ValueError("Invalid storage key")
        return candidate

    async def save(self, file_content: bytes, filename: str) -> str:
        """保存上传文件并返回随机 storage_key."""
        # ① 只保留扩展名, 文件名主体使用 UUID.
        suffix = Path(filename).suffix.lower()
        storage_key = f"{uuid4().hex}{suffix}"
        path = self._path(storage_key)
        # ② 文件写入是阻塞操作, 放到线程池.
        await asyncio.to_thread(path.write_bytes, file_content)
        return storage_key

    async def read(self, storage_key: str) -> bytes:
        """读取文件; 不存在时抛 404."""
        path = self._path(storage_key)

        if not await asyncio.to_thread(path.is_file):
            raise ResourceNotFoundException(
                message="Knowledge document file not found",
                code="KNOWLEDGE_FILE_NOT_FOUND",
            )

        return await asyncio.to_thread(path.read_bytes)

    async def delete(self, storage_key: str) -> None:
        """删除文件; 文件不存在时保持幂等."""
        path = self._path(storage_key)
        if await asyncio.to_thread(path.exists):
            await asyncio.to_thread(path.unlink)
