from io import BytesIO

import pytest
from docx import Document as DocxDocument

from app.core.config import Settings
from app.core.exceptions import ValidationException
from app.services.rag.chunker import Chunker, WhitespaceTokenCounter
from app.services.rag.parser import DocumentParser
from app.services.rag.text_cleaner import clean_text


def test_parser_supports_text_markdown_html_and_docx() -> None:
    parser = DocumentParser()

    text = parser.parse("rules.txt", "退款规则\n\n签收后 7 天可退货。".encode())
    assert text[0].content.startswith("退款规则")

    markdown = parser.parse(
        "rules.md",
        "# 售后规则\n\n签收后 7 天可退货。\n\n## 配送\n\n默认顺丰。".encode(),
    )
    assert any(item.section_title == "售后规则" for item in markdown)
    assert any(item.section_title == "配送" for item in markdown)

    html = parser.parse(
        "rules.html",
        b"<html><body><h1>Rule</h1><script>bad()</script><p>Safe</p></body></html>",
    )
    assert "Safe" in html[0].content
    assert "bad()" not in html[0].content

    docx_buffer = BytesIO()
    docx = DocxDocument()
    docx.add_paragraph("DOCX 退款规则")
    docx.save(docx_buffer)
    docx_parsed = parser.parse("rules.docx", docx_buffer.getvalue())
    assert "DOCX 退款规则" in docx_parsed[0].content


def test_parser_rejects_invalid_files() -> None:
    parser = DocumentParser()

    with pytest.raises(ValidationException):
        parser.parse("rules.exe", b"binary")

    with pytest.raises(ValidationException):
        parser.parse("rules.pdf", b"not a pdf")

    with pytest.raises(ValidationException):
        parser.parse("rules.txt", b"")


def test_clean_text_preserves_meaningful_content() -> None:
    text = "  退款规则\r\n\r\n\r\n金额 100 元。\x00  "
    cleaned = clean_text(text)
    assert cleaned == "退款规则\n\n金额 100 元。"


@pytest.mark.asyncio
async def test_chunker_respects_max_and_indices() -> None:
    settings = Settings(
        _env_file=None,
        rag_chunk_max_tokens=60,
        rag_chunk_target_tokens=50,
        rag_chunk_overlap_tokens=5,
    )
    parser = DocumentParser()
    documents = parser.parse(
        "rules.md",
        (
            "# 退款规则\n\n"
            "签收后七天内可以申请退货退款。退款审核通过后原路退回。\n\n"
            "超过期限的订单需要人工审核。退款金额以实际支付金额为准。\n\n"
            + " ".join(["退款规则说明"] * 40)
        ).encode(),
    )
    chunker = Chunker(settings, WhitespaceTokenCounter())
    chunks = await chunker.chunk(documents)

    assert chunks
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.token_count <= 60 for chunk in chunks)
    assert all(chunk.content.strip() for chunk in chunks)
    assert any(chunk.section_title == "退款规则" for chunk in chunks)
