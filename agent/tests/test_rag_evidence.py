"""TASK-021.2 RAG evidence/no-answer policy tests."""

from __future__ import annotations

import pytest

from agent.rag_evidence import (
    evaluate_rag_evidence,
    evidence_coverage,
)
from agent.tests.fakes import make_item, make_settings


def _item(content: str, score: float):
    return make_item(content=content, score=score)


def test_empty_retrieval_is_not_answerable() -> None:
    decision = evaluate_rag_evidence(
        query="退款规则是什么？",
        items=[],
        settings=make_settings(),
        retrieval_reason="NO_ALLOWED_DOCUMENTS",
    )
    assert decision.answerable is False
    assert decision.reason == "NO_ALLOWED_DOCUMENTS"
    assert decision.top_score is None


def test_low_score_is_rejected() -> None:
    decision = evaluate_rag_evidence(
        query="退款规则是什么？",
        items=[_item("退款需要审核。", 0.55)],
        settings=make_settings(),
    )
    assert decision.answerable is False
    assert decision.reason == "LOW_SCORE"


def test_ambiguous_score_without_evidence_is_rejected() -> None:
    decision = evaluate_rag_evidence(
        query="如何申请退款到区块链钱包？",
        items=[_item("退款申请需要审核。", 0.604)],
        settings=make_settings(),
    )
    assert decision.answerable is False
    assert decision.reason == "LOW_EVIDENCE"
    assert decision.evidence_coverage is not None
    assert decision.evidence_coverage < 0.5


def test_ambiguous_score_with_evidence_is_accepted() -> None:
    decision = evaluate_rag_evidence(
        query="退款审核",
        items=[_item("退款审核需要确认商品状态。", 0.604)],
        settings=make_settings(),
    )
    assert decision.answerable is True
    assert decision.reason == "ACCEPTED"
    assert decision.evidence_coverage is not None
    assert decision.evidence_coverage >= 0.5


def test_high_confidence_is_accepted_even_without_lexical_overlap() -> None:
    decision = evaluate_rag_evidence(
        query="如何申请退款到区块链钱包？",
        items=[_item("退款申请需要审核。", 0.70)],
        settings=make_settings(),
    )
    assert decision.answerable is True
    assert decision.reason == "ACCEPTED"


def test_evidence_coverage_uses_chinese_bigrams() -> None:
    assert evidence_coverage("退款审核", "退款申请需要审核。") >= 0.5
    assert evidence_coverage("区块链钱包", "退款申请需要审核。") == 0.0


def test_empty_query_terms_are_conservative() -> None:
    decision = evaluate_rag_evidence(
        query="？？？",
        items=[_item("退款申请需要审核。", 0.604)],
        settings=make_settings(),
    )
    assert decision.answerable is False
    assert decision.reason == "LOW_EVIDENCE"


@pytest.mark.parametrize(
    ("score", "reason"),
    [
        (0.599, "LOW_SCORE"),
        (0.60, "LOW_EVIDENCE"),
        (0.625, "ACCEPTED"),
    ],
)
def test_score_band_boundaries(score: float, reason: str) -> None:
    decision = evaluate_rag_evidence(
        query="区块链钱包",
        items=[_item("退款申请需要审核。", score)],
        settings=make_settings(),
    )
    assert decision.reason == reason
