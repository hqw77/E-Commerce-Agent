import re

from app.services.rag.parser import ParsedDocument


def clean_text(text: str) -> str:
    """Normalize whitespace while preserving meaningful line breaks."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_documents(documents: list[ParsedDocument]) -> list[ParsedDocument]:
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
