"""RAG 证据充分性与无答案策略.

文件职责:
- 对已经通过 ACL 的检索结果做确定性判断.
- 空结果, 低分和低证据覆盖时拒绝回答.
- 为 Agent 提供可解释的拒答原因.

核心流程:
无结果 -> 低分 -> 模糊分段的词面覆盖检查 -> ACCEPTED.

边界:
本模块不做权限校验, 不替代 RetrievalService 或 MySQL ACL.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.core.config import Settings
from app.schemas.knowledge import RetrievalItem

# 无答案策略的稳定原因码, 会写入 Trace 和调试信息.
RagDecisionReason = Literal[
    "NO_RETRIEVAL",
    "NO_ALLOWED_DOCUMENTS",
    "NO_CANDIDATES",
    "LOW_SCORE",
    "LOW_EVIDENCE",
    "ACCEPTED",
]

# 中文连续片段和拉丁字母数字片段, 用于提取词面证据.
_CJK = re.compile(r"[\u4e00-\u9fff]+")
_LATIN = re.compile(r"[A-Za-z0-9]+")

# 去除高频虚词和业务泛词, 避免它们制造虚假的证据覆盖.
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
    """一次 RAG 证据判断的结果.

    Args:
        answerable: 是否允许进入回答节点.
        reason: 判断原因码.
        top_score: 最高检索分.
        evidence_coverage: 最高分 Chunk 的词面覆盖率.
        min_score: 当前配置的最低分阈值.
        high_confidence_score: 高置信分段边界.
        min_evidence_coverage: 模糊分段要求的最低覆盖率.
    """

    answerable: bool
    reason: RagDecisionReason
    top_score: float | None
    evidence_coverage: float | None
    min_score: float
    high_confidence_score: float
    min_evidence_coverage: float


def _query_terms(query: str) -> set[str]:
    """提取确定性的中文 bigram 和字母数字词.

    这里故意不引入额外 tokenizer, 只作为词面证据信号.

    Args:
        query: 用户问题.

    Returns:
        去重后的证据词集合.
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
    """计算问题证据词在 Chunk 中的覆盖率.

    Args:
        query: 用户问题.
        content: 最高分 Chunk 正文.

    Returns:
        0 到 1 的覆盖率; 没有有效 query 词时返回 0.
    """
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
    """对已授权检索结果执行无答案策略.

    Args:
        query: 用户问题.
        items: 已通过 ACL 的检索结果.
        settings: RAG 阈值配置.
        retrieval_reason: 检索服务返回的诊断原因.

    Returns:
        包含 answerable 和判断依据的 RagEvidenceDecision.
    """
    # ① 空结果直接拒绝, 并保留上游诊断原因.
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

    # ② 最高分仍低于最低阈值时拒绝.
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

    # ③ 分数处于模糊区间时, 还要求词面证据覆盖足够.
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

    # ④ 分数和证据覆盖都满足, 允许进入知识回答.
    return RagEvidenceDecision(
        answerable=True,
        reason="ACCEPTED",
        top_score=top_score,
        evidence_coverage=coverage,
        min_score=settings.agent_rag_min_score,
        high_confidence_score=settings.agent_rag_high_confidence_score,
        min_evidence_coverage=settings.agent_rag_min_evidence_coverage,
    )
