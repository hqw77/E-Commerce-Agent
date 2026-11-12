from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Annotated
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import AsyncSessionLocal, get_db
from app.main import app
from app.models.category import Category
from app.models.product import Product

ADMIN = SimpleNamespace(
    id=1,
    email="admin@example.com",
    is_active=True,
    is_admin=True,
)
REGULAR_USER = SimpleNamespace(
    id=2,
    email="user@example.com",
    is_active=True,
    is_admin=False,
)

CATEGORY_NAME_PREFIX = "it-cat-"
PRODUCT_NO_PREFIX = "ITP"


def install_user(user: SimpleNamespace) -> None:
    """Install a current user that opens the request transaction."""

    async def fake_current_user(
        session: Annotated[AsyncSession, Depends(get_db)],
    ) -> SimpleNamespace:
        await session.execute(text("SELECT 1"))
        return user

    app.dependency_overrides[get_current_user] = fake_current_user


@pytest_asyncio.fixture
async def api_client():
    async def override_get_db():
        async with AsyncSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    install_user(ADMIN)

    created_ids: list[int] = []
    transport = ASGITransport(app=app)

    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            yield client, created_ids
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)

        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(Product).where(Product.product_no.like(f"{PRODUCT_NO_PREFIX}%"))
            )

            # Delete leaves first so the self-referencing FK stays valid.
            while True:
                rows = (
                    await session.execute(
                        select(Category.id, Category.parent_id).where(
                            or_(
                                Category.name.like(f"{CATEGORY_NAME_PREFIX}%"),
                                Category.id.in_(created_ids),
                            )
                        )
                    )
                ).all()

                if not rows:
                    break

                category_ids = {row.id for row in rows}
                parent_ids = {
                    row.parent_id for row in rows if row.parent_id in category_ids
                }
                leaf_ids = [
                    category_id
                    for category_id in category_ids
                    if category_id not in parent_ids
                ]

                if not leaf_ids:
                    break

                await session.execute(delete(Category).where(Category.id.in_(leaf_ids)))

            await session.commit()


async def create_category(
    client: AsyncClient,
    created_ids: list[int],
    *,
    parent_id: int | None = None,
    sort_order: int = 0,
) -> dict:
    response = await client.post(
        "/api/v1/admin/categories",
        json={
            "parent_id": parent_id,
            "name": f"{CATEGORY_NAME_PREFIX}{uuid4().hex[:8]}",
            "sort_order": sort_order,
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    created_ids.append(body["id"])
    return body


async def insert_product(
    *,
    category_id: int,
    status: str = "DRAFT",
) -> None:
    product = Product(
        product_no=f"{PRODUCT_NO_PREFIX}{uuid4().hex[:12].upper()}",
        category_id=category_id,
        name="Category Test Product",
        status=status,
        published_at=(
            datetime.now(UTC).replace(tzinfo=None) if status == "ACTIVE" else None
        ),
    )

    async with AsyncSessionLocal() as session:
        session.add(product)
        await session.commit()


@pytest.mark.asyncio
async def test_create_root_category(api_client) -> None:
    client, created_ids = api_client

    category = await create_category(
        client,
        created_ids,
        sort_order=3,
    )

    assert category["parent_id"] is None
    assert category["status"] == "ENABLED"
    assert category["sort_order"] == 3


@pytest.mark.asyncio
async def test_create_child_category(api_client) -> None:
    client, created_ids = api_client
    parent = await create_category(client, created_ids)

    response = await client.post(
        "/api/v1/admin/categories",
        json={
            "parent_id": parent["id"],
            "name": f"{CATEGORY_NAME_PREFIX}{uuid4().hex[:8]}",
        },
    )

    assert response.status_code == 201
    body = response.json()
    created_ids.append(body["id"])
    assert body["parent_id"] == parent["id"]


@pytest.mark.asyncio
async def test_disabled_parent_cannot_create_child(api_client) -> None:
    client, created_ids = api_client
    parent = await create_category(client, created_ids)

    disable = await client.patch(
        f"/api/v1/admin/categories/{parent['id']}",
        json={"status": "DISABLED"},
    )
    assert disable.status_code == 200

    response = await client.post(
        "/api/v1/admin/categories",
        json={
            "parent_id": parent["id"],
            "name": f"{CATEGORY_NAME_PREFIX}{uuid4().hex[:8]}",
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "CATEGORY_PARENT_DISABLED"


@pytest.mark.asyncio
async def test_list_and_tree(api_client) -> None:
    client, created_ids = api_client
    root_a = await create_category(client, created_ids, sort_order=2)
    child_a = await create_category(
        client,
        created_ids,
        parent_id=root_a["id"],
        sort_order=1,
    )
    root_b = await create_category(client, created_ids, sort_order=1)

    list_response = await client.get("/api/v1/admin/categories")
    assert list_response.status_code == 200
    listed_ids = {item["id"] for item in list_response.json()}
    assert {root_a["id"], child_a["id"], root_b["id"]} <= listed_ids

    tree_response = await client.get("/api/v1/admin/categories/tree")
    assert tree_response.status_code == 200
    tree = tree_response.json()
    roots = {item["id"]: item for item in tree}

    assert roots[root_b["id"]]["children"] == []
    assert roots[root_a["id"]]["children"][0]["id"] == child_a["id"]


@pytest.mark.asyncio
async def test_get_category_detail(api_client) -> None:
    client, created_ids = api_client
    category = await create_category(client, created_ids)

    response = await client.get(f"/api/v1/admin/categories/{category['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == category["id"]


@pytest.mark.asyncio
async def test_update_name_and_sort_order(api_client) -> None:
    client, created_ids = api_client
    category = await create_category(client, created_ids)

    response = await client.patch(
        f"/api/v1/admin/categories/{category['id']}",
        json={"name": "Updated Category", "sort_order": 9},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Updated Category"
    assert body["sort_order"] == 9


@pytest.mark.asyncio
async def test_category_with_product_cannot_create_child(api_client) -> None:
    client, created_ids = api_client
    category = await create_category(client, created_ids)

    await insert_product(category_id=category["id"])

    response = await client.post(
        "/api/v1/admin/categories",
        json={
            "parent_id": category["id"],
            "name": f"{CATEGORY_NAME_PREFIX}{uuid4().hex[:8]}",
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "CATEGORY_HAS_PRODUCTS"


@pytest.mark.asyncio
async def test_enabled_child_prevents_disable(api_client) -> None:
    client, created_ids = api_client
    parent = await create_category(client, created_ids)
    await create_category(
        client,
        created_ids,
        parent_id=parent["id"],
    )

    response = await client.patch(
        f"/api/v1/admin/categories/{parent['id']}",
        json={"status": "DISABLED"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "CATEGORY_HAS_ENABLED_CHILDREN"


@pytest.mark.asyncio
async def test_active_product_prevents_disable(api_client) -> None:
    client, created_ids = api_client
    category = await create_category(client, created_ids)

    await insert_product(category_id=category["id"], status="ACTIVE")

    response = await client.patch(
        f"/api/v1/admin/categories/{category['id']}",
        json={"status": "DISABLED"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "CATEGORY_HAS_ACTIVE_PRODUCTS"


@pytest.mark.asyncio
async def test_disabled_parent_prevents_child_enable(api_client) -> None:
    client, created_ids = api_client
    parent = await create_category(client, created_ids)
    child = await create_category(
        client,
        created_ids,
        parent_id=parent["id"],
    )

    disable_child = await client.patch(
        f"/api/v1/admin/categories/{child['id']}",
        json={"status": "DISABLED"},
    )
    assert disable_child.status_code == 200

    disable_parent = await client.patch(
        f"/api/v1/admin/categories/{parent['id']}",
        json={"status": "DISABLED"},
    )
    assert disable_parent.status_code == 200

    enable_child = await client.patch(
        f"/api/v1/admin/categories/{child['id']}",
        json={"status": "ENABLED"},
    )

    assert enable_child.status_code == 409
    assert enable_child.json()["code"] == "CATEGORY_PARENT_DISABLED"


@pytest.mark.asyncio
async def test_regular_user_gets_403(api_client) -> None:
    client, _created_ids = api_client
    install_user(REGULAR_USER)

    response = await client.post(
        "/api/v1/admin/categories",
        json={"name": f"{CATEGORY_NAME_PREFIX}{uuid4().hex[:8]}"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_anonymous_user_gets_401(api_client) -> None:
    client, _created_ids = api_client
    app.dependency_overrides.pop(get_current_user, None)

    response = await client.post(
        "/api/v1/admin/categories",
        json={"name": f"{CATEGORY_NAME_PREFIX}{uuid4().hex[:8]}"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_missing_category_returns_404(api_client) -> None:
    client, _created_ids = api_client

    response = await client.get("/api/v1/admin/categories/999999999")

    assert response.status_code == 404
    assert response.json()["code"] == "CATEGORY_NOT_FOUND"


@pytest.mark.asyncio
async def test_missing_parent_returns_404(api_client) -> None:
    client, _created_ids = api_client

    response = await client.post(
        "/api/v1/admin/categories",
        json={
            "parent_id": 999999999,
            "name": f"{CATEGORY_NAME_PREFIX}{uuid4().hex[:8]}",
        },
    )

    assert response.status_code == 404
    assert response.json()["code"] == "CATEGORY_PARENT_NOT_FOUND"
