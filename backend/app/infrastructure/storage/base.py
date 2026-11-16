from typing import Protocol


class FileStorage(Protocol):
    """Storage boundary for original knowledge documents."""

    async def save(self, file_content: bytes, filename: str) -> str:
        """Persist bytes and return an opaque storage key."""
        ...

    async def read(self, storage_key: str) -> bytes:
        """Read bytes for a storage key."""
        ...

    async def delete(self, storage_key: str) -> None:
        """Delete a stored file if it exists."""
        ...
