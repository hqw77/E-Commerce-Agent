"""结构优先的文档切分器.

文件职责:
- 把 Parser 输出的段落切成适合 Embedding 的 Chunk.
- 用 BGE tokenizer 计算 token, 而不是按字符数猜.
- 保留页码, 章节和切分版本元数据.

核心流程:
段落 -> 超长段落按句/词拆分 -> 按 max_tokens 聚合
-> 加入 overlap tail -> 生成 ChunkData.
"""

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

# 切分算法版本, 写入 Chunk metadata, 便于后续重建索引时区分.
CHUNKING_VERSION = "structural-v1"


class TokenCounter(Protocol):
    """可替换的 token 计数器接口, 主要用于测试注入."""

    async def count(self, text: str) -> int:
        """计算文本 token 数量."""
        ...


class WhitespaceTokenCounter:
    """按空白切词的确定性计数器, 仅用于显式注入的测试."""

    async def count(self, text: str) -> int:
        """返回空白分隔的词数."""
        return len(re.findall(r"\S+", text))


class BgeTokenCounter:
    """使用 BGE-M3 tokenizer 的计数器."""

    def __init__(self, settings: Settings) -> None:
        """初始化实例依赖."""
        self.settings = settings
        self._tokenizer = None
        self._lock = asyncio.Lock()

    async def _get_tokenizer(self):
        """首次调用时加载 tokenizer, 并发请求只加载一次."""
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
        """用 BGE tokenizer 计算不含特殊符号的 token 数."""
        if not text:
            return 0
        tokenizer = await self._get_tokenizer()
        return len(tokenizer.encode(text, add_special_tokens=False))


@dataclass(frozen=True)
class ChunkData:
    """一个可写入 MySQL 和 Qdrant 的知识 Chunk.

    Args:
        chunk_index: 文档内顺序号.
        content: Chunk 正文.
        token_count: BGE token 数.
        page_number: 来源页码.
        section_title: 来源章节.
        chunk_metadata: 切分版本等附加信息.
    """

    chunk_index: int
    content: str
    token_count: int
    page_number: int | None
    section_title: str | None
    chunk_metadata: dict[str, object]


class Chunker:
    """结构优先, 带 overlap 和确定性索引的 Chunker."""

    def __init__(
        self,
        settings: Settings,
        token_counter: TokenCounter | None = None,
    ) -> None:
        """保存配置, 默认使用 BGE tokenizer."""
        self.settings = settings
        self.token_counter = token_counter or BgeTokenCounter(settings)

    async def chunk(self, documents: list[ParsedDocument]) -> list[ChunkData]:
        """把解析文档切成 Chunk.

        Args:
            documents: Parser 输出的文档列表.

        Returns:
            按阅读顺序排列的 ChunkData.
        """
        units: list[tuple[str, int | None, str | None]] = []

        # ① 先按空行分段, 超长段落继续按句/词拆分.
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

        # ② 按 max_tokens 聚合, 超出时先 emit 并保留 overlap tail.
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
                # overlap 加上新 unit 仍超限时, 丢弃 overlap 重新开始.
                await self._emit(chunks, current)
                current = []
                current_tokens = 0

            current.append(unit)
            current_tokens += unit_tokens

        # ③ 处理最后一批.
        if current:
            await self._emit(chunks, current)

        return chunks

    async def _tokens(
        self,
        units: list[tuple[str, int | None, str | None]],
    ) -> int:
        """计算一组 unit 拼接后的 token 数."""
        return await self.token_counter.count(" ".join(unit[0] for unit in units))

    async def _split_oversized(
        self,
        text: str,
        page_number: int | None,
        section_title: str | None,
    ) -> list[tuple[str, int | None, str | None]]:
        """把超过 max_tokens 的段落按句子或单词继续拆分."""
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
        """取上一 Chunk 尾部不超过 overlap 预算的 unit."""
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
        """把当前 unit 缓冲写成一个 ChunkData."""
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
