from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

from bs4 import BeautifulSoup
from docx import Document as DocxDocument
from pypdf import PdfReader

from app.core.exceptions import ValidationException

PARSER_VERSION = "parsers-v1"
SUPPORTED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".html": "text/html",
    ".htm": "text/html",
}


@dataclass(frozen=True)
class ParsedDocument:
    content: str
    page_number: int | None = None
    section_title: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


class DocumentParser:
    """Extract plain text from supported file types; never execute content."""

    def supports(self, filename: str) -> bool:
        return Path(filename).suffix.lower() in SUPPORTED_EXTENSIONS

    def mime_type_for(self, filename: str) -> str:
        return SUPPORTED_EXTENSIONS.get(
            Path(filename).suffix.lower(),
            "application/octet-stream",
        )

    def validate_file(self, filename: str, content: bytes) -> None:
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise ValidationException(
                message="Unsupported knowledge document type",
                code="KNOWLEDGE_FILE_TYPE_UNSUPPORTED",
            )
        if not content:
            raise ValidationException(
                message="Knowledge document is empty",
                code="KNOWLEDGE_FILE_EMPTY",
            )

        if suffix == ".pdf" and not content.startswith(b"%PDF"):
            raise ValidationException(
                message="Invalid PDF file signature",
                code="KNOWLEDGE_FILE_INVALID",
            )
        if suffix == ".docx" and not content.startswith(b"PK"):
            raise ValidationException(
                message="Invalid DOCX file signature",
                code="KNOWLEDGE_FILE_INVALID",
            )

    def parse(self, filename: str, content: bytes) -> list[ParsedDocument]:
        self.validate_file(filename, content)
        suffix = Path(filename).suffix.lower()

        try:
            if suffix == ".pdf":
                return self._parse_pdf(content)
            if suffix == ".docx":
                return self._parse_docx(content)
            if suffix in {".html", ".htm"}:
                return self._parse_html(content)
            if suffix == ".md":
                return self._parse_markdown(content)
            return [ParsedDocument(content=content.decode("utf-8"))]
        except ValidationException:
            raise
        except Exception as exc:
            raise ValidationException(
                message="Knowledge document parsing failed",
                code="KNOWLEDGE_FILE_PARSE_FAILED",
            ) from exc

    @staticmethod
    def _parse_pdf(content: bytes) -> list[ParsedDocument]:
        reader = PdfReader(BytesIO(content))
        documents: list[ParsedDocument] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                documents.append(
                    ParsedDocument(
                        content=text,
                        page_number=page_number,
                    )
                )
        return documents

    @staticmethod
    def _parse_docx(content: bytes) -> list[ParsedDocument]:
        document = DocxDocument(BytesIO(content))
        paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
        return [ParsedDocument(content="\n\n".join(paragraphs))]

    @staticmethod
    def _parse_html(content: bytes) -> list[ParsedDocument]:
        soup = BeautifulSoup(content, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text("\n")
        return [ParsedDocument(content=text)]

    @staticmethod
    def _parse_markdown(content: bytes) -> list[ParsedDocument]:
        text = content.decode("utf-8")
        sections: list[ParsedDocument] = []
        current_title: str | None = None
        current_lines: list[str] = []

        def flush() -> None:
            if not current_lines:
                return
            body = "\n".join(current_lines).strip()
            if body:
                sections.append(
                    ParsedDocument(
                        content=body,
                        section_title=current_title,
                    )
                )

        for line in text.splitlines():
            if line.startswith("#"):
                flush()
                current_lines = []
                current_title = line.lstrip("#").strip() or None
            else:
                current_lines.append(line)
        flush()

        if not sections and text.strip():
            sections.append(ParsedDocument(content=text))
        return sections
