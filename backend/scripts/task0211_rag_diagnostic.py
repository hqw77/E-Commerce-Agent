"""TASK-021.1 offline RAG diagnostic.

This script is intentionally read-only with respect to the application:
- it does not open MySQL or Qdrant;
- it does not change retrieval code, thresholds, or collections;
- it embeds the TASK-015 evaluation corpus and queries in memory using the
  existing BGE-M3 provider, then simulates threshold/margin policies.

The historical TASK-015 result file does not contain per-result scores, so the
scores used here are a deterministic offline replay of the same 5-document
corpus. The replay's top-1 documents are checked against the historical result.
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
from app.services.rag.embedding import BgeM3EmbeddingProvider

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT / "backend/tests/evaluation/task015_rag_eval_dataset.json"
DEFAULT_RESULT = ROOT / "docs/04-testing/TASK-015/rag-evaluation/task015-rag-results.json"
DEFAULT_KNOWLEDGE = ROOT / "backend/tests/evaluation/knowledge"
DEFAULT_OUTPUT = ROOT / "docs/03-delivery/TASK-021/task0211-rag-diagnostic.json"


def _cosine_top(scores: list[float], k: int) -> list[int]:
    return sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]


def _metrics(
    *,
    rows: list[dict[str, Any]],
    score_threshold: float | None,
    margin_threshold: float | None,
    mode: str,
) -> dict[str, Any]:
    """Apply a no-answer policy and return retrieval/usefulness metrics."""
    rejected_no_answer = 0
    accepted_answerable = 0
    no_answer_count = 0
    answerable_count = 0

    for row in rows:
        top1 = row["top_scores"][0] if row["top_scores"] else 0.0
        top2 = row["top_scores"][1] if len(row["top_scores"]) > 1 else 0.0
        margin = top1 - top2
        if mode == "score":
            reject = score_threshold is not None and top1 < score_threshold
        elif mode == "margin":
            reject = margin_threshold is not None and margin < margin_threshold
        elif mode == "score_and_margin":
            reject = (
                score_threshold is not None
                and margin_threshold is not None
                and (top1 < score_threshold or margin < margin_threshold)
            )
        else:
            reject = False

        if row["answerable"]:
            answerable_count += 1
            if not reject:
                accepted_answerable += 1
        else:
            no_answer_count += 1
            if reject:
                rejected_no_answer += 1

    no_answer_recall = (
        rejected_no_answer / no_answer_count if no_answer_count else 0.0
    )
    answerable_acceptance = (
        accepted_answerable / answerable_count if answerable_count else 0.0
    )
    balanced_accuracy = (no_answer_recall + answerable_acceptance) / 2
    return {
        "mode": mode,
        "score_threshold": score_threshold,
        "margin_threshold": margin_threshold,
        "no_answer_recall": round(no_answer_recall, 6),
        "answerable_acceptance": round(answerable_acceptance, 6),
        "balanced_accuracy": round(balanced_accuracy, 6),
        "rejected_no_answer": rejected_no_answer,
        "accepted_answerable": accepted_answerable,
        "no_answer_count": no_answer_count,
        "answerable_count": answerable_count,
    }


def _sweep(
    rows: list[dict[str, Any]],
    *,
    mode: str,
    thresholds: list[float],
    margin_thresholds: list[float] | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for threshold in thresholds:
        if mode == "score":
            results.append(
                _metrics(
                    rows=rows,
                    score_threshold=threshold,
                    margin_threshold=None,
                    mode=mode,
                )
            )
        else:
            for margin in margin_thresholds or [0.0]:
                results.append(
                    _metrics(
                        rows=rows,
                        score_threshold=(
                            threshold if mode == "score_and_margin" else None
                        ),
                        margin_threshold=margin,
                        mode=mode,
                    )
                )
    return results


def _best(results: list[dict[str, Any]], key: str = "balanced_accuracy") -> dict[str, Any]:
    return max(
        results,
        key=lambda item: (
            item[key],
            item["answerable_acceptance"],
            item["no_answer_recall"],
        ),
    )


def _distribution(values: list[float]) -> dict[str, float]:
    if not values:
        return {}
    return {
        "min": round(min(values), 6),
        "median": round(statistics.median(values), 6),
        "max": round(max(values), 6),
        "mean": round(statistics.fmean(values), 6),
    }


def _roc_auc(rows: list[dict[str, Any]]) -> float:
    """ROC-AUC for score as a no-answer detector (higher = no-answer).

    We use the negative top1 score as the no-answer score, so lower retrieval
    score means more likely no-answer.
    """
    pairs = sorted(
        ((-row["top_scores"][0], not row["answerable"]) for row in rows),
        key=lambda item: item[0],
    )
    positive = sum(1 for _, label in pairs if label)
    negative = len(pairs) - positive
    if positive == 0 or negative == 0:
        return 0.0
    rank_sum = 0.0
    for index, (_, label) in enumerate(pairs, start=1):
        if label:
            rank_sum += index
    return round(
        (rank_sum - positive * (positive + 1) / 2) / (positive * negative),
        6,
    )


async def run() -> dict[str, Any]:
    dataset = json.loads(DEFAULT_DATASET.read_text(encoding="utf-8"))
    historical = json.loads(DEFAULT_RESULT.read_text(encoding="utf-8"))

    document_texts = []
    document_titles = []
    for document in dataset["documents"]:
        path = DEFAULT_KNOWLEDGE / document["file"]
        document_texts.append(path.read_text(encoding="utf-8"))
        document_titles.append(document["title"])

    settings = get_settings()
    provider = BgeM3EmbeddingProvider(settings)
    document_vectors = await provider.embed_documents(document_texts)
    query_vectors = await provider.embed_documents(
        [question["question"] for question in dataset["questions"]]
    )

    rows: list[dict[str, Any]] = []
    replay_top1_matches = 0
    replay_top5_matches = 0
    for question, query_vector in zip(
        dataset["questions"], query_vectors, strict=True
    ):
        raw_scores = [
            sum(a * b for a, b in zip(query_vector, doc_vector, strict=True))
            for doc_vector in document_vectors
        ]
        order = _cosine_top(raw_scores, 5)
        top_documents = [document_titles[index] for index in order]
        top_scores = [round(raw_scores[index], 6) for index in order]
        historical_top = historical["details"][len(rows)]["returned_documents"]
        historical_top = [
            title.removeprefix("rag-eval-") for title in historical_top
        ]
        if top_documents[0] == historical_top[0]:
            replay_top1_matches += 1
        if set(top_documents) == set(historical_top):
            replay_top5_matches += 1
        rows.append(
            {
                "id": question["id"],
                "question": question["question"],
                "answerable": bool(question["answerable"]),
                "expected_document": question["expected_document"],
                "top_documents": top_documents,
                "top_scores": top_scores,
                "top1_hit": top_documents[0] == question["expected_document"],
                "replay_top1_matches_historical": top_documents[0]
                == historical_top[0],
            }
        )

    answerable_rows = [row for row in rows if row["answerable"]]
    no_answer_rows = [row for row in rows if not row["answerable"]]
    answerable_top1 = [row["top_scores"][0] for row in answerable_rows]
    no_answer_top1 = [row["top_scores"][0] for row in no_answer_rows]
    answerable_margin = [
        row["top_scores"][0] - row["top_scores"][1] for row in answerable_rows
    ]
    no_answer_margin = [
        row["top_scores"][0] - row["top_scores"][1] for row in no_answer_rows
    ]

    thresholds = [round(0.10 + index * 0.01, 2) for index in range(76)]
    score_sweep = _sweep(rows, mode="score", thresholds=thresholds)
    margin_thresholds = [round(index * 0.005, 3) for index in range(61)]
    margin_sweep = _sweep(
        rows,
        mode="margin",
        thresholds=[0.0],
        margin_thresholds=margin_thresholds,
    )
    combined_sweep = _sweep(
        rows,
        mode="score_and_margin",
        thresholds=[round(0.20 + index * 0.01, 2) for index in range(51)],
        margin_thresholds=[round(index * 0.01, 2) for index in range(16)],
    )

    no_answer_max = max(no_answer_top1)
    reject_all_no_answer = [
        item
        for item in score_sweep
        if item["no_answer_recall"] == 1.0
        and item["score_threshold"] is not None
        and item["score_threshold"] > no_answer_max
    ]
    best_reject_all = max(
        reject_all_no_answer,
        key=lambda item: item["answerable_acceptance"],
    ) if reject_all_no_answer else None

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": "offline diagnostic only; no DB/Qdrant/application changes",
        "dataset": {
            "path": str(DEFAULT_DATASET.relative_to(ROOT)),
            "version": dataset["version"],
            "documents": len(dataset["documents"]),
            "questions": len(dataset["questions"]),
            "answerable": len(answerable_rows),
            "no_answer": len(no_answer_rows),
        },
        "historical_result": {
            "path": str(DEFAULT_RESULT.relative_to(ROOT)),
            "top_k": historical["top_k"],
            "embedding_model": historical["embedding_model"],
            "collection": historical["collection"],
        },
        "offline_replay": {
            "embedding_model": settings.rag_embedding_model,
            "embedding_dimension": settings.rag_embedding_dimension,
            "document_texts": len(document_texts),
            "queries": len(query_vectors),
            "top1_match_historical": replay_top1_matches,
            "top5_set_match_historical": replay_top5_matches,
            "top1_total": len(rows),
            "top1_accuracy_answerable": round(
                sum(row["top1_hit"] for row in answerable_rows)
                / len(answerable_rows),
                6,
            ),
            "note": (
                "Historical result file has no score field; scores are a "
                "deterministic in-memory replay using the existing BGE-M3 "
                "provider and the same 5-document corpus."
            ),
        },
        "score_distribution": {
            "answerable_top1": _distribution(answerable_top1),
            "no_answer_top1": _distribution(no_answer_top1),
            "answerable_margin": _distribution(answerable_margin),
            "no_answer_margin": _distribution(no_answer_margin),
            "score_roc_auc_no_answer": _roc_auc(rows),
        },
        "score_sweep": score_sweep,
        "margin_sweep": margin_sweep,
        "combined_sweep": combined_sweep,
        "best": {
            "score_balanced": _best(score_sweep),
            "margin_balanced": _best(margin_sweep),
            "combined_balanced": _best(combined_sweep),
            "score_reject_all_no_answer": best_reject_all,
        },
        "rows": rows,
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
    print(json.dumps({
        "output": str(args.output),
        "dataset": result["dataset"],
        "replay": result["offline_replay"],
        "best": result["best"],
        "score_distribution": result["score_distribution"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
