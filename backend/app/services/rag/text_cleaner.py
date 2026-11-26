"""知识文档文本清洗.

文件职责:
- 统一换行符, 删除 NUL 和控制空白.
- 合并多余空格和空行.
- 丢弃清洗后为空的 ParsedDocument.

核心边界:
保留有意义的段落换行, 不改变正文语义.
"""

import re

from app.services.rag.parser import ParsedDocument


def clean_text(text: str) -> str:
    """清洗单个文本片段并返回去首尾空白的结果."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_documents(documents: list[ParsedDocument]) -> list[ParsedDocument]:
    """批量清洗文档, 保留页码, 章节和 metadata."""
    cleaned: list[ParsedDocument] = []
    for document in documents:
        content = clean_text(document.content)
        if content:
            cleaned.append(
                ParsedDocument(
                    content=content,
                    page_number=document.page_number,
                    section_title=document.section_title,
                    metadata=document.metadata,
                )
            )
    return cleaned
