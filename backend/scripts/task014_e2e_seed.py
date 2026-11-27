r"""TASK-014 E2E fixture seed and cleanup.

This is test tooling, not production code. It generates random test credentials,
creates only the resources it records, and writes them to an ignored local file.
It never truncates a table or deletes data it did not create.

Usage (from repository root):

    $env:PYTHONPATH="$PWD\backend;$PWD"
    .venv\Scripts\python.exe backend/scripts/task014_e2e_seed.py
    .venv\Scripts\python.exe backend/scripts/task014_e2e_seed.py --with-knowledge
    .venv\Scripts\python.exe backend/scripts/task014_e2e_seed.py --cleanup

Optional environment variables:

    E2E_API_BASE_URL=http://127.0.0.1:8000/api/v1
    E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD
    E2E_USER_EMAIL / E2E_USER_PASSWORD
    E2E_OUTPUT=frontend/.tmp/task014-e2e.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from app.core.security import hash_password
from app.db.redis import redis_client
from app.db.session import AsyncSessionLocal
from app.models.category import Category
from app.models.inventory import Inventory
from app.models.inventory_transaction import InventoryTransaction
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_document_version import KnowledgeDocumentVersion
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.sku import Sku
from app.models.user import User, normalize_email
from sqlalchemy import delete, select

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "frontend" / ".tmp" / "task014-e2e.json"
DEFAULT_FIXTURE = ROOT / "docs" / "04-testing" / "TASK-014" / "fixtures" / "task014-refund-policy.md"
API_BASE = os.getenv("E2E_API_BASE_URL", "http://127.0.0.1:8000/api/v1")
PREFIX = os.getenv("E2E_PREFIX", "TASK014")


def _email(prefix: str) -> str:
    return normalize_email(f"{PREFIX}-{prefix}-{uuid4().hex[:10]}@example.com")


def _password() -> str:
    return secrets.token_urlsafe(24)


async def _request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    token: str | None = None,
    json_body: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    expected: set[int] | None = None,
) -> Any:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = await client.request(
        method,
        path,
        headers=headers,
        json=json_body,
        files=files,
        data=data,
    )
    expected = expected or {200, 201}
    if response.status_code not in expected:
        raise RuntimeError(f"{method} {path} failed: {response.status_code} {response.text[:500]}")
    if response.content:
        return response.json()
    return None


async def _login(client: httpx.AsyncClient, email: str, password: str) -> str:
    data = await _request(
        client,
        "POST",
        "/auth/login",
        json_body={"email": email, "password": password},
    )
    return str(data["access_token"])


async def seed(with_knowledge: bool = False) -> None:
    output = Path(os.getenv("E2E_OUTPUT", str(DEFAULT_OUTPUT)))
    output.parent.mkdir(parents=True, exist_ok=True)
    admin_email = os.getenv("E2E_ADMIN_EMAIL") or _email("admin")
    admin_password = os.getenv("E2E_ADMIN_PASSWORD") or _password()
    user_email = os.getenv("E2E_USER_EMAIL") or _email("user")
    user_password = os.getenv("E2E_USER_PASSWORD") or _password()

    async with AsyncSessionLocal() as session:
        admin = User(
            email=normalize_email(admin_email),
            password_hash=hash_password(admin_password),
            is_active=True,
            is_admin=True,
        )
        user = User(
            email=normalize_email(user_email),
            password_hash=hash_password(user_password),
            is_active=True,
            is_admin=False,
        )
        session.add_all([admin, user])
        await session.commit()
        await session.refresh(admin)
        await session.refresh(user)
        admin_id, user_id = admin.id, user.id

    async with httpx.AsyncClient(base_url=API_BASE, timeout=300.0) as client:
        admin_token = await _login(client, admin_email, admin_password)
        user_token = await _login(client, user_email, user_password)

        category = await _request(
            client,
            "POST",
            "/admin/categories",
            token=admin_token,
            json_body={"name": f"{PREFIX}-CAT-{uuid4().hex[:8]}", "sort_order": 0},
        )
        product = await _request(
            client,
            "POST",
            "/admin/products",
            token=admin_token,
            json_body={
                "product_no": f"{PREFIX}-P-{uuid4().hex[:8].upper()}",
                "category_id": category["id"],
                "name": f"{PREFIX} Product {uuid4().hex[:6]}",
                "description": "TASK-014 E2E fixture",
                "skus": [
                    {
                        "sku_code": f"{PREFIX}-SKU-{uuid4().hex[:8].upper()}",
                        "attributes": {"color": "black"},
                        "price": 19.9,
                    }
                ],
            },
        )
        sku = product["skus"][0]
        await _request(client, "POST", f"/admin/products/{product['id']}/activate", token=admin_token)
        await _request(
            client,
            "POST",
            f"/admin/inventory/{sku['id']}/stock-in",
            token=admin_token,
            json_body={"quantity": 5, "idempotency_key": f"{PREFIX}-STOCK-{uuid4().hex}"},
        )
        order = await _request(
            client,
            "POST",
            "/orders",
            token=user_token,
            json_body={
                "items": [{"sku_code": sku["sku_code"], "quantity": 1}],
                "receiver_name": f"{PREFIX} User",
                "receiver_phone": "13800000000",
                "receiver_address": f"{PREFIX} Test Road 1",
                "idempotency_key": f"{PREFIX}-ORDER-{uuid4().hex}",
            },
        )

        document = None
        version = None
        if with_knowledge and DEFAULT_FIXTURE.exists():
            content = DEFAULT_FIXTURE.read_bytes()
            document = await _request(
                client,
                "POST",
                "/knowledge/documents",
                token=admin_token,
                files={"file": (DEFAULT_FIXTURE.name, content, "text/markdown")},
                data={
                    "title": f"{PREFIX}-KB-{uuid4().hex[:8]}",
                    "description": "TASK-014 E2E RAG fixture",
                    "visibility": "PUBLIC",
                },
            )
            if document.get("versions"):
                version = document["versions"][0]

    fixture = {
        "run_id": uuid4().hex,
        "created_at": datetime.now(UTC).isoformat(),
        "admin": {"id": admin_id, "email": admin_email, "password": admin_password},
        "user": {"id": user_id, "email": user_email, "password": user_password},
        "category": {"id": category["id"], "name": category["name"]},
        "product": {"id": product["id"], "product_no": product["product_no"]},
        "sku": {"id": sku["id"], "sku_code": sku["sku_code"]},
        "order": {"order_no": order["order_no"]},
        "knowledge": {
            "document_id": document["id"] if document else None,
            "version_id": version["id"] if version else None,
            "version_status": version["status"] if version else None,
        },
        "status": "seeded",
    }
    output.write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"fixture_written={output}")
    print(f"run_id={fixture['run_id']}")
    print(f"order_no={fixture['order']['order_no']}")
    print(f"knowledge_status={fixture['knowledge']['version_status']}")



async def seed_knowledge() -> None:
    """Upload the RAG fixture for an existing seeded run."""
    output = Path(os.getenv("E2E_OUTPUT", str(DEFAULT_OUTPUT)))
    if not output.exists():
        raise SystemExit(f"fixture not found: {output}")
    fixture = json.loads(output.read_text(encoding="utf-8"))
    if not DEFAULT_FIXTURE.exists():
        raise SystemExit(f"knowledge fixture not found: {DEFAULT_FIXTURE}")
    content = DEFAULT_FIXTURE.read_bytes()
    async with httpx.AsyncClient(base_url=API_BASE, timeout=1800.0) as client:
        token = await _login(
            client,
            fixture["admin"]["email"],
            fixture["admin"]["password"],
        )
        document = await _request(
            client,
            "POST",
            "/knowledge/documents",
            token=token,
            files={"file": (DEFAULT_FIXTURE.name, content, "text/markdown")},
            data={
                "title": f"{PREFIX}-KB-{uuid4().hex[:8]}",
                "description": "TASK-014 E2E RAG fixture",
                "visibility": "PUBLIC",
            },
        )
    version = document["versions"][0] if document.get("versions") else None
    fixture["knowledge"] = {
        "document_id": document["id"],
        "version_id": version["id"] if version else None,
        "version_status": version["status"] if version else None,
    }
    output.write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"knowledge_seeded document_id={document['id']}")
    print(f"version_status={fixture['knowledge']['version_status']}")


async def cleanup() -> None:
    output = Path(os.getenv("E2E_OUTPUT", str(DEFAULT_OUTPUT)))
    if not output.exists():
        raise SystemExit(f"fixture not found: {output}")
    fixture = json.loads(output.read_text(encoding="utf-8"))
    admin = fixture["admin"]
    user = fixture["user"]
    knowledge = fixture.get("knowledge", {})
    document_id = knowledge.get("document_id")

    # Delete through the API first so Qdrant vectors and storage cleanup run.
    try:
        async with httpx.AsyncClient(base_url=API_BASE, timeout=300.0) as client:
            token = await _login(client, admin["email"], admin["password"])
            if document_id:
                await _request(
                    client,
                    "DELETE",
                    f"/knowledge/documents/{document_id}",
                    token=token,
                    expected={200, 204, 404},
                )
    except Exception as exc:  # noqa: BLE001 - cleanup reports and continues DB cleanup
        print(f"api_cleanup_warning={type(exc).__name__}:{exc}")

    async with AsyncSessionLocal() as session:
        order = (
            await session.execute(
                select(Order).where(Order.order_no == fixture["order"]["order_no"])
            )
        ).scalar_one_or_none()
        if order is not None:
            await session.execute(delete(OrderItem).where(OrderItem.order_id == order.id))
            await session.execute(delete(Order).where(Order.id == order.id))
        sku_id = fixture["sku"]["id"]
        await session.execute(delete(InventoryTransaction).where(InventoryTransaction.sku_id == sku_id))
        await session.execute(delete(Inventory).where(Inventory.sku_id == sku_id))
        await session.execute(delete(Sku).where(Sku.id == sku_id))
        await session.execute(delete(Product).where(Product.id == fixture["product"]["id"]))
        await session.execute(delete(Category).where(Category.id == fixture["category"]["id"]))
        # Browser tests may create one UI-only category with this run's exact name.
        await session.execute(
            delete(Category).where(Category.name.like(f"{PREFIX}-UI-%"))
        )
        if document_id:
            await session.execute(
                delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id)
            )
            await session.execute(
                delete(KnowledgeDocumentVersion).where(KnowledgeDocumentVersion.document_id == document_id)
            )
            await session.execute(delete(KnowledgeDocument).where(KnowledgeDocument.id == document_id))
        await session.execute(delete(User).where(User.id.in_([admin["id"], user["id"]])))
        await session.commit()

    for user_id in (admin["id"], user["id"]):
        keys = [key async for key in redis_client.scan_iter(f"agent:*:{user_id}:*")]
        if keys:
            await redis_client.delete(*keys)
    output.unlink(missing_ok=True)
    print(f"cleanup_done run_id={fixture['run_id']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="TASK-014 E2E fixture tool")
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument(
        "--with-knowledge",
        action="store_true",
        help="Also upload the RAG fixture; may require the BGE-M3 model download.",
    )
    parser.add_argument(
        "--knowledge-only",
        action="store_true",
        help="Upload the RAG fixture for an existing seeded run.",
    )
    args = parser.parse_args()
    if args.cleanup:
        asyncio.run(cleanup())
    elif args.knowledge_only:
        asyncio.run(seed_knowledge())
    else:
        asyncio.run(seed(args.with_knowledge))


if __name__ == "__main__":
    main()
    sys.exit(0)
