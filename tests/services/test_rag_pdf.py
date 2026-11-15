from io import BytesIO

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

from app.core.exceptions import ValidationException
from app.services.rag.parser import DocumentParser

pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))


def build_pdf(*pages: str) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    for text in pages:
        if text:
            pdf.setFont("STSong-Light", 12)
            pdf.drawString(72, 750, text)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def test_pdf_parser_extracts_chinese_and_multiple_pages() -> None:
    content = build_pdf(
        "退款规则：签收后七天内可以申请退货退款。",
        "配送规则：默认使用顺丰配送。",
    )

    documents = DocumentParser().parse("rules.pdf", content)

    assert [document.page_number for document in documents] == [1, 2]
    assert "七天内" in documents[0].content
    assert "顺丰" in documents[1].content


def test_pdf_parser_returns_empty_for_blank_pdf() -> None:
    content = build_pdf("", "")

    documents = DocumentParser().parse("blank.pdf", content)

    assert documents == []


def test_pdf_parser_rejects_corrupted_pdf() -> None:
    with pytest.raises(ValidationException):
        DocumentParser().parse("broken.pdf", b"%PDF-1.4 broken")
