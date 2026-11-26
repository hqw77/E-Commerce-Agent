"""知识文档解析器.

文件职责:
- 校验 PDF/DOCX/Markdown/TXT/HTML 文件类型和签名.
- 提取纯文本, 页码和 Markdown 章节.
- 不执行文档中的任何脚本或宏.

核心边界:
解析后的正文还会经过 text_cleaner 和 Chunker.
"""

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

from bs4 import BeautifulSoup
from docx import Document as DocxDocument
from pypdf import PdfReader

from app.core.exceptions import ValidationException

# 解析算法版本, 写入版本记录便于重建索引.
PARSER_VERSION = "parsers-v1"

# 支持的扩展名到 MIME 类型映射.
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
    """解析后的一个文本单元.

    Args:
        content: 提取出的纯文本.
        page_number: PDF 页码, 其他类型可为空.
        section_title: Markdown 章节标题.
        metadata: 解析附加信息.
    """

    content: str
    page_number: int | None = None
    section_title: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


class DocumentParser:
    """从支持的文件类型中提取纯文本, 绝不执行内容."""

    def supports(self, filename: str) -> bool:
        """判断扩展名是否受支持."""
        return Path(filename).suffix.lower() in SUPPORTED_EXTENSIONS

    def mime_type_for(self, filename: str) -> str:
        """返回扩展名对应的 MIME, 未知类型回退为二进制."""
        return SUPPORTED_EXTENSIONS.get(
            Path(filename).suffix.lower(),
            "application/octet-stream",
        )

    def validate_file(self, filename: str, content: bytes) -> None:
        """校验扩展名, 非空和 PDF/DOCX 文件头."""
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
        """按扩展名分发解析并统一包装解析异常."""
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
        """逐页提取 PDF 文本, 跳过空白页."""
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
        """提取 DOCX 段落并用空行拼接."""
        document = DocxDocument(BytesIO(content))
        paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
        return [ParsedDocument(content="\n\n".join(paragraphs))]

    @staticmethod
    def _parse_html(content: bytes) -> list[ParsedDocument]:
        """移除 script/style 后提取 HTML 可见文本."""
        soup = BeautifulSoup(content, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text("\n")
        return [ParsedDocument(content=text)]

    @staticmethod
    def _parse_markdown(content: bytes) -> list[ParsedDocument]:
        """按标题行切分 Markdown 章节."""
        text = content.decode("utf-8")
        sections: list[ParsedDocument] = []
        current_title: str | None = None
        current_lines: list[str] = []

        def flush() -> None:
            """把当前章节缓冲写入 sections."""
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
