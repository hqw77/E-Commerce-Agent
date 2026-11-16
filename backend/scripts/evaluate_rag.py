"""Repeatable RAG retrieval evaluation.

Run from the repository root:

    python backend/scripts/evaluate_rag.py

The script creates a temporary set of knowledge documents in the configured
MySQL/Qdrant instance, runs the real BGE-M3 retrieval stack, writes metrics,
and removes its test data unless --keep is supplied.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal, engine
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_document_version import KnowledgeDocumentVersion
from app.models.user import User
from app.services.rag.document_service import KnowledgeDocumentService
from app.services.rag.retrieval_service import KnowledgeRetrievalService
from app.services.rag.runtime import (
    get_chunker,
    get_embedding_provider,
    get_vector_store,
)
from sqlalchemy import delete

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger(__name__)
DEFAULT_DATASET = ROOT / "tests" / "evaluation" / "rag_eval_dataset.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "docs" / "03-delivery" / "TASK-005" / "rag-evaluation-results.json"
TITLE_PREFIX = "rag-eval-"


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def load_dataset(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def metrics(
    rows: list[dict[str, Any]],
    top_k: int,
) -> dict[str, float]:
    """Calculate answerable, no-answer, and keyword-level retrieval metrics."""
    answerable_rows = [row for row in rows if row["answerable"]]
    no_answer_rows = [row for row in rows if not row["answerable"]]
    total = len(rows)
    recall = 0.0
    reciprocal_rank = 0.0
    precision = 0.0
    empty = 0
    keyword_hits = 0
    keyword_rows = 0

    for row in answerable_rows:
        expected = row["expected_document"]
        titles = [item.document_title for item in row["results"]]
        relevant = [title == expected for title in titles]
        rank = next(
            (index + 1 for index, is_relevant in enumerate(relevant) if is_relevant),
            0,
        )
        recall += 1.0 if rank else 0.0
        reciprocal_rank += 1.0 / rank if rank else 0.0
        precision += sum(relevant) / top_k
        keywords = row.get("expected_keywords") or []
        if keywords:
            keyword_rows += 1
            contents = " ".join(item.content for item in row["results"])
            if any(keyword in contents for keyword in keywords):
                keyword_hits += 1

    for row in rows:
        if not row["results"]:
            empty += 1

    no_answer_empty = sum(1 for row in no_answer_rows if not row["results"])
    answerable_total = len(answerable_rows)

    return {
        "recall_at_k": recall / answerable_total if answerable_total else 0.0,
        "recall_at_5": recall / answerable_total if answerable_total else 0.0,
        "mrr": reciprocal_rank / answerable_total if answerable_total else 0.0,
        "precision_at_k": precision / answerable_total if answerable_total else 0.0,
        "precision_at_5": precision / answerable_total if answerable_total else 0.0,
        "empty_retrieval_rate": empty / total if total else 0.0,
        "no_answer_accuracy": no_answer_empty / len(no_answer_rows) if no_answer_rows else 0.0,
        "chunk_keyword_hit_rate": keyword_hits / keyword_rows if keyword_rows else 0.0,
        "queries": float(total),
        "answerable_queries": float(answerable_total),
        "no_answer_queries": float(len(no_answer_rows)),
    }


async def evaluate(
    dataset_path: Path,
    output_path: Path,
    top_k: int,
    keep: bool,
) -> int:
    dataset_path = dataset_path.resolve()
    output_path = output_path.resolve()
    settings = get_settings()
    dataset = load_dataset(dataset_path)
    documents = dataset["documents"]
    questions = dataset["questions"]

    embedding = get_embedding_provider(settings)
    vector_store = get_vector_store(settings)
    chunker = get_chunker(settings)
    created_documents: list[KnowledgeDocument] = []
    storage_keys: list[str] = []
    admin_id: int | None = None

    async with AsyncSessionLocal() as session:
        admin = User(
            email=f"{TITLE_PREFIX}admin-{uuid4().hex[:8]}@example.com",
            password_hash="x",
            is_active=True,
            is_admin=True,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        admin_id = admin.id
        admin_user = SimpleNamespace(
            id=admin.id,
            email=admin.email,
            is_active=True,
            is_admin=True,
        )

        service = KnowledgeDocumentService(
            session,
            settings,
            chunker=chunker,
            embedding=embedding,
            vector_store=vector_store,
        )
        retrieval = KnowledgeRetrievalService(
            session,
            settings,
            embedding=embedding,
            vector_store=vector_store,
        )

        try:
            for document_spec in documents:
                title = f"{TITLE_PREFIX}{document_spec['title']}"
                content = (dataset_path.parent / "knowledge" / document_spec["file"]).read_bytes()
                document = await service.create_document(
                    user=admin_user,
                    title=title,
                    description="RAG evaluation fixture",
                    visibility="PUBLIC",
                    original_filename=document_spec["file"],
                    content=content,
                )
                created_documents.append(document)
                for version in document.versions:
                    storage_keys.append(version.storage_key)
                latest = max(document.versions, key=lambda version: version.version_no)
                await service.publish_version(
                    user=admin_user,
                    document_id=document.id,
                    version_id=latest.id,
                )

            rows: list[dict[str, Any]] = []
            for question in questions:
                results = await retrieval.retrieve(
                    user=admin_user,
                    query=question["question"],
                    top_k=top_k,
                )
                expected = question.get("expected_document")
                expected_document = (
                    f"{TITLE_PREFIX}{expected}" if expected else None
                )
                rows.append(
                    {
                        "id": question["id"],
                        "question": question["question"],
                        "answerable": question.get("answerable", expected_document is not None),
                        "expected_document": expected_document,
                        "expected_keywords": question.get("expected_keywords", []),
                        "results": results,
                    }
                )

            summary = metrics(rows, top_k)
            output = {
                "generated_at": utc_now(),
                "dataset": str(dataset_path.relative_to(ROOT)),
                "dataset_version": dataset.get("version", "unversioned"),
                "top_k": top_k,
                "embedding_model": settings.rag_embedding_model,
                "collection": settings.rag_collection,
                "metrics": summary,
                "details": [
                    {
                        "id": row["id"],
                        "question": row["question"],
                        "answerable": row["answerable"],
                        "expected_document": row["expected_document"],
                        "expected_keywords": row["expected_keywords"],
                        "returned_documents": [
                            item.document_title for item in row["results"]
                        ],
                        "returned_chunk_ids": [
                            item.chunk_id for item in row["results"]
                        ],
                    }
                    for row in rows
                ],
            }
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(output, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            print(f"result={output_path}")
            return 0
        finally:
            if not keep:
                for document in created_documents:
                    try:
                        await service.delete_document(
                            user=admin_user,
                            document_id=document.id,
                        )
                    except Exception as exc:  # noqa: BLE001 - best-effort cleanup
                        logger.warning("evaluation document cleanup failed: %s", exc)
                if created_documents:
                    document_ids = [document.id for document in created_documents]
                    await session.execute(
                        delete(KnowledgeChunk).where(
                            KnowledgeChunk.document_id.in_(document_ids)
                        )
                    )
                    await session.execute(
                        delete(KnowledgeDocumentVersion).where(
                            KnowledgeDocumentVersion.document_id.in_(document_ids)
                        )
                    )
                    await session.execute(
                        delete(KnowledgeDocument).where(
                            KnowledgeDocument.id.in_(document_ids)
                        )
                    )
                if admin_id is not None:
                    await session.execute(
                        delete(User).where(User.id == admin_id)
                    )
                await session.commit()
                for storage_key in storage_keys:
                    try:
                        await service.storage.delete(storage_key)
                    except Exception as exc:  # noqa: BLE001 - best-effort cleanup
                        logger.warning("evaluation file cleanup failed: %s", exc)
            await vector_store.close()
            await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate RAG retrieval")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep evaluation documents for inspection",
    )
    args = parser.parse_args()
    code = asyncio.run(
        evaluate(
            dataset_path=args.dataset,
            output_path=args.output,
            top_k=args.top_k,
            keep=args.keep,
        )
    )
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


if __name__ == "__main__":
    main()
