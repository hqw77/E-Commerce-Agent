import asyncio
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from transformers import AutoTokenizer

from app.core.config import Settings
from app.core.exceptions import AppException
from app.services.rag.parser import ParsedDocument

CHUNKING_VERSION = "structural-v1"


class TokenCounter(Protocol):
    async def count(self, text: str) -> int: ...


class WhitespaceTokenCounter:
    """Deterministic fallback used only when a tokenizer is explicitly injected."""

    async def count(self, text: str) -> int:
        return len(re.findall(r"\S+", text))


class BgeTokenCounter:
    """Token counter using the BGE-M3 tokenizer, not raw character counts."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._tokenizer = None
        self._lock = asyncio.Lock()

    async def _get_tokenizer(self):
        if self._tokenizer is not None:
            return self._tokenizer

        async with self._lock:
            if self._tokenizer is not None:
                return self._tokenizer
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
                self._tokenizer = await asyncio.to_thread(
                    AutoTokenizer.from_pretrained,
                    self.settings.rag_embedding_model,
                    cache_dir=cache_dir,
                )
            except Exception as exc:
                raise AppException(
                    message="BGE-M3 tokenizer is unavailable",
                    code="RAG_TOKENIZER_UNAVAILABLE",
                    status_code=503,
                ) from exc
            return self._tokenizer

    async def count(self, text: str) -> int:
        if not text:
            return 0
        tokenizer = await self._get_tokenizer()
        return len(tokenizer.encode(text, add_special_tokens=False))


@dataclass(frozen=True)
class ChunkData:
    chunk_index: int
    content: str
    token_count: int
    page_number: int | None
    section_title: str | None
    chunk_metadata: dict[str, object]


class Chunker:
    """Structure-first, overlap-aware chunker with deterministic indices."""

    def __init__(
        self,
        settings: Settings,
        token_counter: TokenCounter | None = None,
    ) -> None:
        self.settings = settings
        self.token_counter = token_counter or BgeTokenCounter(settings)

    async def chunk(self, documents: list[ParsedDocument]) -> list[ChunkData]:
        units: list[tuple[str, int | None, str | None]] = []

        for document in documents:
            paragraphs = [
                paragraph.strip()
                for paragraph in re.split(r"\n\s*\n", document.content)
                if paragraph.strip()
            ]
            for paragraph in paragraphs:
                units.extend(
                    await self._split_oversized(
                        paragraph,
                        document.page_number,
                        document.section_title,
                    )
                )

        if not units:
            return []

        chunks: list[ChunkData] = []
        current: list[tuple[str, int | None, str | None]] = []
        current_tokens = 0

        for unit in units:
            unit_tokens = await self.token_counter.count(unit[0])

            if current and current_tokens + unit_tokens > self.settings.rag_chunk_max_tokens:
                await self._emit(chunks, current)
                current = await self._overlap_tail(current)
                current_tokens = await self._tokens(current)

            if (
                current
                and current_tokens + unit_tokens
                > self.settings.rag_chunk_max_tokens
            ):
                # An overlap plus a unit can still exceed the max; drop overlap.
                await self._emit(chunks, current)
                current = []
                current_tokens = 0

            current.append(unit)
            current_tokens += unit_tokens

        if current:
            await self._emit(chunks, current)

        return chunks

    async def _tokens(
        self,
        units: list[tuple[str, int | None, str | None]],
    ) -> int:
        return await self.token_counter.count(" ".join(unit[0] for unit in units))

    async def _split_oversized(
        self,
        text: str,
        page_number: int | None,
        section_title: str | None,
    ) -> list[tuple[str, int | None, str | None]]:
        if await self.token_counter.count(text) <= self.settings.rag_chunk_max_tokens:
            return [(text, page_number, section_title)]

        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[。！？.!?])\s+|\n+", text)
            if sentence.strip()
        ]
        units: list[tuple[str, int | None, str | None]] = []
        buffer = ""

        for sentence in sentences:
            candidate = f"{buffer} {sentence}".strip() if buffer else sentence
            if await self.token_counter.count(candidate) <= self.settings.rag_chunk_max_tokens:
                buffer = candidate
                continue

            if buffer:
                units.append((buffer, page_number, section_title))
            buffer = sentence

            if await self.token_counter.count(buffer) > self.settings.rag_chunk_max_tokens:
                words = buffer.split()
                word_buffer: list[str] = []
                for word in words:
                    candidate_words = [*word_buffer, word]
                    if await self.token_counter.count(" ".join(candidate_words)) > self.settings.rag_chunk_max_tokens:
                        if word_buffer:
                            units.append((" ".join(word_buffer), page_number, section_title))
                        word_buffer = [word]
                    else:
                        word_buffer.append(word)
                buffer = " ".join(word_buffer)

        if buffer:
            units.append((buffer, page_number, section_title))
        return units

    async def _overlap_tail(
        self,
        units: list[tuple[str, int | None, str | None]],
    ) -> list[tuple[str, int | None, str | None]]:
        if self.settings.rag_chunk_overlap_tokens <= 0:
            return []

        tail: list[tuple[str, int | None, str | None]] = []
        for unit in reversed(units):
            candidate = [unit, *tail]
            if await self._tokens(candidate) > self.settings.rag_chunk_overlap_tokens:
                break
            tail = candidate
        return tail

    async def _emit(
        self,
        chunks: list[ChunkData],
        units: list[tuple[str, int | None, str | None]],
    ) -> None:
        content = "\n".join(unit[0] for unit in units).strip()
        if not content:
            return

        token_count = await self.token_counter.count(content)
        if token_count <= 0:
            return

        first = units[0]
        chunks.append(
            ChunkData(
                chunk_index=len(chunks),
                content=content,
                token_count=token_count,
                page_number=first[1],
                section_title=first[2],
                chunk_metadata={
                    "chunking_version": CHUNKING_VERSION,
                    "unit_count": len(units),
                },
            )
        )
