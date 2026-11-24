"""Deterministic RAG evidence/no-answer policy.

The policy is intentionally lexical and model-free:

1. Reject empty retrieval.
2. Reject a top score below the low-confidence boundary.
3. In the ambiguous score band, require lexical evidence coverage.
4. Accept high-confidence retrieval.

This is a policy layer at the Agent boundary. It does not replace ACL checks,
Backend Service authorization, or the raw ``/knowledge/retrieve`` API.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.core.config import Settings
from app.schemas.knowledge import RetrievalItem

RagDecisionReason = Literal[
    "NO_RETRIEVAL",
    "NO_ALLOWED_DOCUMENTS",
    "NO_CANDIDATES",
    "LOW_SCORE",
    "LOW_EVIDENCE",
    "ACCEPTED",
]

_CJK = re.compile(r"[\u4e00-\u9fff]+")
_LATIN = re.compile(r"[A-Za-z0-9]+")
_STOP_TERMS = frozenset(
    {
        "如何",
        "什么",
        "多少",
        "哪些",
        "可以",
        "是否",
        "需要",
        "怎么",
        "怎样",
        "请问",
        "我的",
        "一下",
        "这个",
        "那个",
        "今天",
        "明天",
        "现在",
        "还是",
        "就是",
        "以及",
        "还有",
        "的话",
        "时候",
        "我们",
        "你们",
        "他们",
        "一个",
        "能够",
        "支持",
        "进行",
        "申请",
        "订单",
        "商品",
        "平台",
        "规则",
        "政策",
        "说明",
        "使用",
        "问题",
        "吗",
        "呢",
        "的",
        "了",
        "是",
        "在",
        "和",
        "与",
        "或",
        "有",
        "无",
        "不",
        "我",
        "你",
        "他",
        "它",
        "这",
        "那",
        "会",
        "能",
        "要",
        "到",
        "为",
        "多少天",
    }
)


@dataclass(frozen=True, slots=True)
class RagEvidenceDecision:
    answerable: bool
    reason: RagDecisionReason
    top_score: float | None
    evidence_coverage: float | None
    min_score: float
    high_confidence_score: float
    min_evidence_coverage: float


def _query_terms(query: str) -> set[str]:
    """Extract deterministic Chinese bigrams and alphanumeric terms.

    This deliberately avoids a new tokenizer/model dependency. It is an
    evidence signal, not a semantic entailment model.
    """
    terms: set[str] = set()
    for sequence in _CJK.findall(query.casefold()):
        for index in range(len(sequence) - 1):
            bigram = sequence[index : index + 2]
            if bigram not in _STOP_TERMS:
                terms.add(bigram)
    for token in _LATIN.findall(query.casefold()):
        if len(token) >= 2 and token not in _STOP_TERMS:
            terms.add(token)
    return terms


def evidence_coverage(query: str, content: str) -> float:
    """Fraction of query evidence terms present in the top chunk."""
    terms = _query_terms(query)
    if not terms:
        return 0.0
    normalized = content.casefold()
    return sum(1 for term in terms if term in normalized) / len(terms)


def evaluate_rag_evidence(
    *,
    query: str,
    items: list[RetrievalItem],
    settings: Settings,
    retrieval_reason: str | None = None,
) -> RagEvidenceDecision:
    """Apply the no-answer policy to already-authorized retrieval items.

    ``retrieval_reason`` is an optional diagnostic from the retrieval service;
    the policy does not perform permission checks itself.
    """
    if not items:
        reason: RagDecisionReason
        if retrieval_reason == "NO_ALLOWED_DOCUMENTS":
            reason = "NO_ALLOWED_DOCUMENTS"
        elif retrieval_reason == "NO_CANDIDATES":
            reason = "NO_CANDIDATES"
        else:
            reason = "NO_RETRIEVAL"
        return RagEvidenceDecision(
            answerable=False,
            reason=reason,
            top_score=None,
            evidence_coverage=None,
            min_score=settings.agent_rag_min_score,
            high_confidence_score=settings.agent_rag_high_confidence_score,
            min_evidence_coverage=settings.agent_rag_min_evidence_coverage,
        )

    top = max(items, key=lambda item: item.score)
    top_score = float(top.score)
    if top_score < settings.agent_rag_min_score:
        return RagEvidenceDecision(
            answerable=False,
            reason="LOW_SCORE",
            top_score=top_score,
            evidence_coverage=evidence_coverage(query, top.content),
            min_score=settings.agent_rag_min_score,
            high_confidence_score=settings.agent_rag_high_confidence_score,
            min_evidence_coverage=settings.agent_rag_min_evidence_coverage,
        )

    coverage = evidence_coverage(query, top.content)
    if (
        top_score < settings.agent_rag_high_confidence_score
        and coverage < settings.agent_rag_min_evidence_coverage
    ):
        return RagEvidenceDecision(
            answerable=False,
            reason="LOW_EVIDENCE",
            top_score=top_score,
            evidence_coverage=coverage,
            min_score=settings.agent_rag_min_score,
            high_confidence_score=settings.agent_rag_high_confidence_score,
            min_evidence_coverage=settings.agent_rag_min_evidence_coverage,
        )

    return RagEvidenceDecision(
        answerable=True,
        reason="ACCEPTED",
        top_score=top_score,
        evidence_coverage=coverage,
        min_score=settings.agent_rag_min_score,
        high_confidence_score=settings.agent_rag_high_confidence_score,
        min_evidence_coverage=settings.agent_rag_min_evidence_coverage,
    )
