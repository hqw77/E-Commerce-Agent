"""Small operational commands for the RAG knowledge base.

The first version deliberately avoids a task queue. These commands are for
recovering failed versions and checking MySQL/Qdrant consistency.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.infrastructure.vector.qdrant import QdrantVectorStore
from app.models.knowledge_document_version import KnowledgeDocumentVersion
from app.repositories.knowledge import KnowledgeChunkRepository
from app.services.rag.document_service import KnowledgeDocumentService


async def check_consistency() -> int:
    """检查 MySQL 与 Qdrant 的索引一致性."""
    settings = get_settings()
    vector_store = QdrantVectorStore(settings)
    failures = 0
    try:
        async with AsyncSessionLocal() as session:
            versions = list(
                (
                    await session.execute(
                        select(KnowledgeDocumentVersion).where(
                            KnowledgeDocumentVersion.status.in_(
                                {"INDEXED", "PUBLISHED"}
                            )
                        )
                    )
                ).scalars()
            )
            chunks = KnowledgeChunkRepository(session)
            for version in versions:
                mysql_count = await chunks.count_by_version(version.id)
                qdrant_count = await vector_store.count_by_version(version.id)
                if mysql_count != qdrant_count:
                    failures += 1
                    print(
                        f"MISMATCH version={version.id} "
                        f"mysql={mysql_count} qdrant={qdrant_count}"
                    )
                else:
                    print(
                        f"OK version={version.id} chunks={mysql_count}"
                    )
    finally:
        await vector_store.close()
    return 1 if failures else 0


async def retry_failed() -> int:
    """重试失败的文档版本."""
    settings = get_settings()
    vector_store = QdrantVectorStore(settings)
    try:
        async with AsyncSessionLocal() as session:
            versions = list(
                (
                    await session.execute(
                        select(KnowledgeDocumentVersion).where(
                            KnowledgeDocumentVersion.status == "FAILED"
                        )
                    )
                ).scalars()
            )
            service = KnowledgeDocumentService(
                session,
                settings,
                vector_store=vector_store,
            )
            for version in versions:
                try:
                    processed = await service.process_version(
                        version.document_id,
                        version.id,
                    )
                    print(
                        f"RETRIED version={processed.id} "
                        f"status={processed.status}"
                    )
                except Exception as exc:  # noqa: BLE001 - CLI reports per version
                    print(
                        f"RETRY_FAILED version={version.id} "
                        f"error={type(exc).__name__}"
                    )
    finally:
        await vector_store.close()
    return 0


async def list_pending() -> int:
    """列出未完成处理的文档版本."""
    async with AsyncSessionLocal() as session:
        versions = list(
            (
                await session.execute(
                    select(KnowledgeDocumentVersion).where(
                        KnowledgeDocumentVersion.status.in_(
                            {"UPLOADED", "PROCESSING"}
                        )
                    )
                )
            ).scalars()
        )
        for version in versions:
            print(
                f"PENDING version={version.id} "
                f"document={version.document_id} status={version.status}"
            )
    return 0


def main() -> None:
    """RAG 运维 CLI 入口."""
    parser = argparse.ArgumentParser(description="RAG knowledge operations")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("check", help="check MySQL/Qdrant chunk counts")
    subcommands.add_parser("retry-failed", help="retry FAILED versions")
    subcommands.add_parser("pending", help="list UPLOADED/PROCESSING versions")
    args = parser.parse_args()

    if args.command == "check":
        raise SystemExit(asyncio.run(check_consistency()))
    if args.command == "retry-failed":
        raise SystemExit(asyncio.run(retry_failed()))
    if args.command == "pending":
        raise SystemExit(asyncio.run(list_pending()))
    parser.error("unknown command")


if __name__ == "__main__":
    main()
    sys.exit(0)
