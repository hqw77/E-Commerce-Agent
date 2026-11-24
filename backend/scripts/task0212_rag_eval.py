"""TASK-021.2 offline RAG evaluation and ACL/no-answer diagnosis.

The script is read-only with respect to MySQL/Qdrant. It embeds the expanded
versioned evaluation corpus (including one ADMIN_ONLY document) in memory and
simulates PUBLIC-user and ADMIN retrieval scopes.

It records Top-K document IDs, synthetic chunk IDs and similarity scores so the
policy can be audited. Synthetic IDs are deliberately not database IDs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.schemas.knowledge import RetrievalItem
from app.services.rag.embedding import BgeM3EmbeddingProvider

from agent.rag_evidence import evaluate_rag_evidence

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT / "backend/tests/evaluation/task0212_rag_eval_dataset.json"
DEFAULT_OLD_DATASET = ROOT / "backend/tests/evaluation/task015_rag_eval_dataset.json"
DEFAULT_KNOWLEDGE = ROOT / "backend/tests/evaluation/knowledge"
DEFAULT_OUTPUT = ROOT / "docs/03-delivery/TASK-021/task0212-rag-eval-results.json"


def _top_indices(scores: list[float], k: int) -> list[int]:
    return sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]


def _wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    import math

    z = 1.96
    p = k / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return (round(center - margin, 4), round(center + margin, 4))


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    answerable = [row for row in rows if row["answerable"]]
    no_answer = [row for row in rows if not row["answerable"]]
    rejected_no_answer = sum(1 for row in no_answer if not row["accepted"])
    accepted_answerable = sum(1 for row in answerable if row["accepted"])
    return {
        "queries": len(rows),
        "answerable": len(answerable),
        "no_answer": len(no_answer),
        "no_answer_rejection_rate": (
            round(rejected_no_answer / len(no_answer), 4) if no_answer else 0.0
        ),
        "answerable_acceptance_rate": (
            round(accepted_answerable / len(answerable), 4)
            if answerable
            else 0.0
        ),
        "false_rejection_count": len(answerable) - accepted_answerable,
        "false_rejection_rate": (
            round((len(answerable) - accepted_answerable) / len(answerable), 4)
            if answerable
            else 0.0
        ),
        "no_answer_rejection_wilson_95": _wilson(
            rejected_no_answer, len(no_answer)
        ),
        "answerable_acceptance_wilson_95": _wilson(
            accepted_answerable, len(answerable)
        ),
        "reason_counts": {
            reason: sum(1 for row in rows if row["reason"] == reason)
            for reason in sorted({row["reason"] for row in rows})
        },
    }


def _baseline_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    answerable = [row for row in rows if row["answerable"]]
    no_answer = [row for row in rows if not row["answerable"]]
    return {
        "queries": len(rows),
        "answerable": len(answerable),
        "no_answer": len(no_answer),
        "no_answer_rejection_rate": 0.0,
        "answerable_acceptance_rate": 1.0,
        "false_rejection_count": 0,
        "false_rejection_rate": 0.0,
    }


def _score_distribution(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    values = [row[key] for row in rows if row.get(key) is not None]
    if not values:
        return {}
    return {
        "min": round(min(values), 6),
        "median": round(statistics.median(values), 6),
        "max": round(max(values), 6),
        "mean": round(statistics.fmean(values), 6),
    }


def _serialize_item(item: RetrievalItem) -> dict[str, Any]:
    return {
        "document_id": item.document_id,
        "chunk_id": item.chunk_id,
        "document_title": item.document_title,
        "score": round(item.score, 6),
    }


async def run() -> dict[str, Any]:
    dataset = json.loads(DEFAULT_DATASET.read_text(encoding="utf-8"))
    old_dataset = json.loads(DEFAULT_OLD_DATASET.read_text(encoding="utf-8"))
    old_ids = {question["id"] for question in old_dataset["questions"]}

    docs: list[dict[str, Any]] = []
    for index, documentation in enumerate(dataset["documents"], start=1):
        content = (DEFAULT_KNOWLEDGE / documentation["file"]).read_text(
            encoding="utf-8"
        )
        docs.append(
            {
                "document_id": index,
                "chunk_id": 1000 + index,
                "title": documentation["title"],
                "visibility": documentation.get("visibility", "PUBLIC"),
                "content": content,
            }
        )

    settings = get_settings()
    embedding = BgeM3EmbeddingProvider(settings)
    doc_vectors = await embedding.embed_documents(
        [documentation["content"] for documentation in docs]
    )
    query_vectors = await embedding.embed_documents(
        [question["question"] for question in dataset["questions"]]
    )

    roles: dict[str, dict[str, Any]] = {}
    for role in ("user", "admin"):
        allowed_docs = [
            documentation
            for documentation in docs
            if role == "admin" or documentation["visibility"] == "PUBLIC"
        ]
        rows: list[dict[str, Any]] = []
        for question, query_vector in zip(
            dataset["questions"], query_vectors, strict=True
        ):
            scores = [
                sum(a * b for a, b in zip(query_vector, document_vector, strict=True))
                for document_vector in doc_vectors
            ]
            allowed_indices = [
                docs.index(documentation) for documentation in allowed_docs
            ]
            ranked = _top_indices(
                [scores[index] for index in allowed_indices],
                min(5, len(allowed_indices)),
            )
            items = [
                RetrievalItem(
                    chunk_id=allowed_docs[ranked_index]["chunk_id"],
                    document_id=allowed_docs[ranked_index]["document_id"],
                    version_id=1,
                    document_title=allowed_docs[ranked_index]["title"],
                    content=allowed_docs[ranked_index]["content"],
                    score=scores[allowed_indices[ranked_index]],
                    page_number=None,
                    section_title=None,
                    original_filename="offline-eval",
                )
                for ranked_index in ranked
            ]
            expected = question.get("expected_document")
            access_denied = (
                role == "user"
                and question.get("visibility") == "ADMIN_ONLY"
            )
            if access_denied:
                decision = {
                    "answerable": False,
                    "reason": "NO_ALLOWED_DOCUMENTS",
                    "top_score": None,
                    "evidence_coverage": None,
                }
                accepted = False
                category = "acl_filtered"
            else:
                decision_obj = evaluate_rag_evidence(
                    query=question["question"],
                    items=items,
                    settings=settings,
                    retrieval_reason="OK" if items else "NO_CANDIDATES",
                )
                decision = {
                    "answerable": decision_obj.answerable,
                    "reason": decision_obj.reason,
                    "top_score": decision_obj.top_score,
                    "evidence_coverage": decision_obj.evidence_coverage,
                }
                accepted = decision_obj.answerable
                category = question.get("category", "answerable")
            rows.append(
                {
                    "id": question["id"],
                    "question": question["question"],
                    "answerable": bool(question["answerable"]),
                    "category": category,
                    "visibility": question.get("visibility", "PUBLIC"),
                    "expected_document": expected,
                    "expected_document_in_scope": (
                        expected is None
                        or any(documentation["title"] == expected for documentation in allowed_docs)
                    ),
                    "access_denied": access_denied,
                    "accepted": accepted,
                    "reason": decision["reason"],
                    "top_score": decision["top_score"],
                    "evidence_coverage": decision["evidence_coverage"],
                    "top_k": [_serialize_item(item) for item in items],
                }
            )
        # ACL rows are evaluated separately; they are not normal no-answer data.
        normal_rows = [
            row
            for row in rows
            if row["category"] != "acl" and not row["access_denied"]
        ]
        acl_rows = [
            row
            for row in rows
            if row["category"] == "acl" or row["access_denied"]
        ]
        old_rows = [row for row in normal_rows if row["id"] in old_ids]
        roles[role] = {
            "normal": _metrics(normal_rows),
            "baseline": _baseline_metrics(normal_rows),
            "old_subset": _metrics(old_rows),
            "acl": {
                "count": len(acl_rows),
                "filtered": sum(1 for row in acl_rows if row["access_denied"]),
                "expected_in_scope": sum(
                    1 for row in acl_rows if row["expected_document_in_scope"]
                ),
            },
            "score_distribution": {
                "answerable_top1": _score_distribution(
                    [row for row in normal_rows if row["answerable"]],
                    "top_score",
                ),
                "no_answer_top1": _score_distribution(
                    [row for row in normal_rows if not row["answerable"]],
                    "top_score",
                ),
            },
            "rows": rows,
        }

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": "offline read-only evaluation; no MySQL/Qdrant/application changes",
        "dataset": {
            "path": str(DEFAULT_DATASET.relative_to(ROOT)),
            "version": dataset["version"],
            "documents": len(docs),
            "questions": len(dataset["questions"]),
            "answerable": sum(1 for question in dataset["questions"] if question["answerable"]),
            "no_answer": sum(1 for question in dataset["questions"] if not question["answerable"]),
            "acl": sum(1 for question in dataset["questions"] if question.get("category") == "acl"),
        },
        "old_dataset": {
            "path": str(DEFAULT_OLD_DATASET.relative_to(ROOT)),
            "version": old_dataset["version"],
            "questions": len(old_dataset["questions"]),
        },
        "policy": {
            "name": "score-band-plus-lexical-evidence",
            "min_score": settings.agent_rag_min_score,
            "high_confidence_score": settings.agent_rag_high_confidence_score,
            "min_evidence_coverage": settings.agent_rag_min_evidence_coverage,
            "note": (
                "Offline candidate, not production-certified. Lexical evidence "
                "coverage is a Chinese-bigram overlap heuristic."
            ),
        },
        "roles": roles,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = asyncio.run(run())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "dataset": result["dataset"],
                "policy": result["policy"],
                "user": {
                    "normal": result["roles"]["user"]["normal"],
                    "old_subset": result["roles"]["user"]["old_subset"],
                    "acl": result["roles"]["user"]["acl"],
                },
                "admin": {
                    "normal": result["roles"]["admin"]["normal"],
                    "acl": result["roles"]["admin"]["acl"],
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
