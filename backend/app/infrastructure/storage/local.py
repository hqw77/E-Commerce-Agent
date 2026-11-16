import asyncio
from pathlib import Path
from uuid import uuid4

from app.core.config import Settings
from app.core.exceptions import ResourceNotFoundException


class LocalFileStorage:
    """Local filesystem implementation of the FileStorage boundary."""

    def __init__(self, settings: Settings) -> None:
        self.root = Path(settings.rag_storage_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, storage_key: str) -> Path:
        candidate = (self.root / storage_key).resolve()
        if candidate.parent != self.root:
            raise ValueError("Invalid storage key")
        return candidate

    async def save(self, file_content: bytes, filename: str) -> str:
        suffix = Path(filename).suffix.lower()
        storage_key = f"{uuid4().hex}{suffix}"
        path = self._path(storage_key)
        await asyncio.to_thread(path.write_bytes, file_content)
        return storage_key

    async def read(self, storage_key: str) -> bytes:
        path = self._path(storage_key)

        if not await asyncio.to_thread(path.is_file):
            raise ResourceNotFoundException(
                message="Knowledge document file not found",
                code="KNOWLEDGE_FILE_NOT_FOUND",
            )

        return await asyncio.to_thread(path.read_bytes)

    async def delete(self, storage_key: str) -> None:
        path = self._path(storage_key)
        if await asyncio.to_thread(path.exists):
            await asyncio.to_thread(path.unlink)
