from types import SimpleNamespace
from typing import Annotated
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import AsyncSessionLocal, get_db
from app.main import app
from app.models.category import Category
from app.models.inventory import Inventory
from app.models.inventory_transaction import InventoryTransaction
from app.models.product import Product
from app.models.sku import Sku

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

CATEGORY_PREFIX = "it-cat-"
PRODUCT_PREFIX = "ITP"
SKU_PREFIX = "ITS"


def install_user(user: SimpleNamespace) -> None:
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

    transport = ASGITransport(app=app)

    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)

        async with AsyncSessionLocal() as session:
            product_ids = list(
                (
                    await session.execute(
                        select(Product.id).where(
                            Product.product_no.like(f"{PRODUCT_PREFIX}%")
                        )
                    )
                ).scalars()
            )

            if product_ids:
                sku_ids = list(
                    (
                        await session.execute(
                            select(Sku.id).where(Sku.product_id.in_(product_ids))
                        )
                    ).scalars()
                )

                if sku_ids:
                    await session.execute(
                        delete(InventoryTransaction).where(
                            InventoryTransaction.sku_id.in_(sku_ids)
                        )
                    )
                    await session.execute(
                        delete(Inventory).where(Inventory.sku_id.in_(sku_ids))
                    )

                await session.execute(
                    delete(Sku).where(Sku.product_id.in_(product_ids))
                )
                await session.execute(
                    delete(Product).where(Product.id.in_(product_ids))
                )

            while True:
                rows = (
                    await session.execute(
                        select(Category.id, Category.parent_id).where(
                            Category.name.like(f"{CATEGORY_PREFIX}%")
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


def new_product_no() -> str:
    return f"{PRODUCT_PREFIX}{uuid4().hex[:12].upper()}"


def new_sku_code() -> str:
    return f"{SKU_PREFIX}{uuid4().hex[:12].upper()}"


async def create_category(client: AsyncClient) -> dict:
    response = await client.post(
        "/api/v1/admin/categories",
        json={
            "name": f"{CATEGORY_PREFIX}{uuid4().hex[:8]}",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_product(
    client: AsyncClient,
    category_id: int,
    *,
    product_no: str | None = None,
    name: str = "Product",
    skus: list[dict] | None = None,
) -> dict:
    response = await client.post(
        "/api/v1/admin/products",
        json={
            "product_no": product_no or new_product_no(),
            "category_id": category_id,
            "name": name,
            "skus": skus or [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_sku(
    client: AsyncClient,
    product_id: int,
    *,
    sku_code: str | None = None,
    attributes: dict[str, str] | None = None,
    price: str = "9.99",
    status: str | None = None,
) -> dict:
    payload = {
        "sku_code": sku_code or new_sku_code(),
        "attributes": attributes or {"color": "red"},
        "price": price,
    }

    if status is not None:
        payload["status"] = status

    response = await client.post(
        f"/api/v1/admin/products/{product_id}/skus",
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def inventory_snapshot(sku_id: int) -> tuple[Inventory | None, int]:
    async with AsyncSessionLocal() as session:
        inventory = (
            await session.execute(select(Inventory).where(Inventory.sku_id == sku_id))
        ).scalar_one_or_none()
        transaction_count = (
            (
                await session.execute(
                    select(InventoryTransaction).where(
                        InventoryTransaction.sku_id == sku_id
                    )
                )
            )
            .scalars()
            .all()
        )
        return inventory, len(transaction_count)


@pytest.mark.asyncio
async def test_create_product(api_client) -> None:
    category = await create_category(api_client)
    product = await create_product(
        api_client,
        category["id"],
        name="Normal Product",
    )

    assert product["status"] == "DRAFT"
    assert product["category_id"] == category["id"]
    assert product["skus"] == []


@pytest.mark.asyncio
async def test_duplicate_product_no_rejected(api_client) -> None:
    category = await create_category(api_client)
    product_no = new_product_no()
    await create_product(
        api_client,
        category["id"],
        product_no=product_no,
    )

    response = await api_client.post(
        "/api/v1/admin/products",
        json={
            "product_no": product_no,
            "category_id": category["id"],
            "name": "Duplicate",
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "PRODUCT_NO_CONFLICT"


@pytest.mark.asyncio
async def test_missing_category_rejected(api_client) -> None:
    response = await api_client.post(
        "/api/v1/admin/products",
        json={
            "product_no": new_product_no(),
            "category_id": 999999999,
            "name": "Missing Category",
        },
    )

    assert response.status_code == 404
    assert response.json()["code"] == "CATEGORY_NOT_FOUND"


@pytest.mark.asyncio
async def test_disabled_category_rejected(api_client) -> None:
    category = await create_category(api_client)

    disable = await api_client.patch(
        f"/api/v1/admin/categories/{category['id']}",
        json={"status": "DISABLED"},
    )
    assert disable.status_code == 200

    response = await api_client.post(
        "/api/v1/admin/products",
        json={
            "product_no": new_product_no(),
            "category_id": category["id"],
            "name": "Disabled Category",
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "CATEGORY_DISABLED"


@pytest.mark.asyncio
async def test_non_leaf_category_rejected(api_client) -> None:
    parent = await create_category(api_client)
    child = await api_client.post(
        "/api/v1/admin/categories",
        json={
            "parent_id": parent["id"],
            "name": f"{CATEGORY_PREFIX}{uuid4().hex[:8]}",
        },
    )
    assert child.status_code == 201

    response = await api_client.post(
        "/api/v1/admin/products",
        json={
            "product_no": new_product_no(),
            "category_id": parent["id"],
            "name": "Non Leaf",
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "CATEGORY_NOT_LEAF"


@pytest.mark.asyncio
async def test_product_list_filters_and_pagination(api_client) -> None:
    category = await create_category(api_client)
    alpha = await create_product(
        api_client,
        category["id"],
        name="Alpha Widget",
    )
    beta = await create_product(
        api_client,
        category["id"],
        name="Beta Gadget",
        skus=[
            {
                "sku_code": new_sku_code(),
                "attributes": {"color": "blue"},
                "price": "10.00",
            }
        ],
    )
    activate = await api_client.post(f"/api/v1/admin/products/{beta['id']}/activate")
    assert activate.status_code == 200

    page = await api_client.get(
        "/api/v1/admin/products",
        params={
            "category_id": category["id"],
            "page": 1,
            "page_size": 1,
        },
    )
    assert page.status_code == 200
    assert page.json()["total"] == 2
    assert len(page.json()["items"]) == 1

    keyword = await api_client.get(
        "/api/v1/admin/products",
        params={"category_id": category["id"], "keyword": "Alpha"},
    )
    assert [item["id"] for item in keyword.json()["items"]] == [alpha["id"]]

    active = await api_client.get(
        "/api/v1/admin/products",
        params={
            "category_id": category["id"],
            "status": "ACTIVE",
        },
    )
    assert [item["id"] for item in active.json()["items"]] == [beta["id"]]

    draft = await api_client.get(
        "/api/v1/admin/products",
        params={
            "category_id": category["id"],
            "status": "DRAFT",
        },
    )
    assert [item["id"] for item in draft.json()["items"]] == [alpha["id"]]


@pytest.mark.asyncio
async def test_product_detail_contains_skus_and_inventory(api_client) -> None:
    category = await create_category(api_client)
    product = await create_product(
        api_client,
        category["id"],
        skus=[
            {
                "sku_code": new_sku_code(),
                "attributes": {"color": "red"},
                "price": "9.99",
            }
        ],
    )

    response = await api_client.get(f"/api/v1/admin/products/{product['id']}")

    assert response.status_code == 200
    body = response.json()
    assert len(body["skus"]) == 1
    assert body["skus"][0]["inventory"] == {
        "sku_id": body["skus"][0]["id"],
        "total_quantity": 0,
        "reserved_quantity": 0,
        "available_quantity": 0,
    }


@pytest.mark.asyncio
async def test_update_product_name_and_description(api_client) -> None:
    category = await create_category(api_client)
    product = await create_product(api_client, category["id"])

    response = await api_client.patch(
        f"/api/v1/admin/products/{product['id']}",
        json={
            "name": "Updated Product",
            "description": "Updated description",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Updated Product"
    assert body["description"] == "Updated description"

    clear = await api_client.patch(
        f"/api/v1/admin/products/{product['id']}",
        json={"description": None},
    )
    assert clear.status_code == 200
    assert clear.json()["description"] is None


@pytest.mark.asyncio
async def test_draft_and_inactive_product_can_change_category(
    api_client,
) -> None:
    first = await create_category(api_client)
    second = await create_category(api_client)
    product = await create_product(api_client, first["id"])

    draft_change = await api_client.patch(
        f"/api/v1/admin/products/{product['id']}",
        json={"category_id": second["id"]},
    )
    assert draft_change.status_code == 200
    assert draft_change.json()["category_id"] == second["id"]

    await api_client.post(
        f"/api/v1/admin/products/{product['id']}/skus",
        json={
            "sku_code": new_sku_code(),
            "attributes": {"color": "red"},
            "price": "9.99",
        },
    )
    activate = await api_client.post(f"/api/v1/admin/products/{product['id']}/activate")
    assert activate.status_code == 200

    deactivate = await api_client.post(
        f"/api/v1/admin/products/{product['id']}/deactivate"
    )
    assert deactivate.status_code == 200

    inactive_change = await api_client.patch(
        f"/api/v1/admin/products/{product['id']}",
        json={"category_id": first["id"]},
    )
    assert inactive_change.status_code == 200
    assert inactive_change.json()["category_id"] == first["id"]


@pytest.mark.asyncio
async def test_invalid_product_no_format_rejected(api_client) -> None:
    category = await create_category(api_client)

    response = await api_client.post(
        "/api/v1/admin/products",
        json={
            "product_no": "bad",
            "category_id": category["id"],
            "name": "Invalid Product No",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_PRODUCT_NO"


@pytest.mark.asyncio
async def test_active_product_cannot_change_category(api_client) -> None:
    first = await create_category(api_client)
    second = await create_category(api_client)
    product = await create_product(
        api_client,
        first["id"],
        skus=[
            {
                "sku_code": new_sku_code(),
                "attributes": {"color": "red"},
                "price": "9.99",
            }
        ],
    )
    activate = await api_client.post(f"/api/v1/admin/products/{product['id']}/activate")
    assert activate.status_code == 200

    response = await api_client.patch(
        f"/api/v1/admin/products/{product['id']}",
        json={"category_id": second["id"]},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "PRODUCT_STATUS_CONFLICT"


@pytest.mark.asyncio
async def test_update_to_disabled_category_rejected(api_client) -> None:
    first = await create_category(api_client)
    second = await create_category(api_client)
    product = await create_product(api_client, first["id"])

    disable = await api_client.patch(
        f"/api/v1/admin/categories/{second['id']}",
        json={"status": "DISABLED"},
    )
    assert disable.status_code == 200

    response = await api_client.patch(
        f"/api/v1/admin/products/{product['id']}",
        json={"category_id": second["id"]},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "CATEGORY_DISABLED"


@pytest.mark.asyncio
async def test_product_transitions_and_archive_terminal(api_client) -> None:
    category = await create_category(api_client)
    product = await create_product(api_client, category["id"])

    cannot_activate = await api_client.post(
        f"/api/v1/admin/products/{product['id']}/activate"
    )
    assert cannot_activate.status_code == 409
    assert cannot_activate.json()["code"] == "PRODUCT_NOT_PUBLISHABLE"

    await create_sku(api_client, product["id"])

    activate = await api_client.post(f"/api/v1/admin/products/{product['id']}/activate")
    assert activate.status_code == 200
    assert activate.json()["status"] == "ACTIVE"
    assert activate.json()["published_at"] is not None

    deactivate = await api_client.post(
        f"/api/v1/admin/products/{product['id']}/deactivate"
    )
    assert deactivate.status_code == 200
    assert deactivate.json()["status"] == "INACTIVE"
    assert deactivate.json()["published_at"] is not None

    archive = await api_client.post(f"/api/v1/admin/products/{product['id']}/archive")
    assert archive.status_code == 200
    assert archive.json()["status"] == "ARCHIVED"
    assert archive.json()["archived_at"] is not None

    archive_again = await api_client.post(
        f"/api/v1/admin/products/{product['id']}/archive"
    )
    assert archive_again.status_code == 409
    assert archive_again.json()["code"] == "PRODUCT_ARCHIVED"

    activate_archived = await api_client.post(
        f"/api/v1/admin/products/{product['id']}/activate"
    )
    assert activate_archived.status_code == 409
    assert activate_archived.json()["code"] == "PRODUCT_ARCHIVED"

    update_archived = await api_client.patch(
        f"/api/v1/admin/products/{product['id']}",
        json={"name": "Cannot change"},
    )
    assert update_archived.status_code == 409
    assert update_archived.json()["code"] == "PRODUCT_ARCHIVED"


@pytest.mark.asyncio
async def test_invalid_status_transition(api_client) -> None:
    category = await create_category(api_client)
    product = await create_product(api_client, category["id"])

    response = await api_client.post(
        f"/api/v1/admin/products/{product['id']}/deactivate"
    )

    assert response.status_code == 409
    assert response.json()["code"] == "PRODUCT_STATUS_CONFLICT"


@pytest.mark.asyncio
async def test_category_disabled_blocks_activation(api_client) -> None:
    category = await create_category(api_client)
    product = await create_product(
        api_client,
        category["id"],
        skus=[
            {
                "sku_code": new_sku_code(),
                "attributes": {"color": "red"},
                "price": "9.99",
            }
        ],
    )

    disable = await api_client.patch(
        f"/api/v1/admin/categories/{category['id']}",
        json={"status": "DISABLED"},
    )
    assert disable.status_code == 200

    activate = await api_client.post(f"/api/v1/admin/products/{product['id']}/activate")

    assert activate.status_code == 409
    assert activate.json()["code"] == "CATEGORY_DISABLED"


@pytest.mark.asyncio
async def test_create_sku_creates_zero_inventory_without_ledger(
    api_client,
) -> None:
    category = await create_category(api_client)
    product = await create_product(api_client, category["id"])
    sku = await create_sku(api_client, product["id"])

    inventory, ledger_count = await inventory_snapshot(sku["id"])

    assert inventory is not None
    assert inventory.total_quantity == 0
    assert inventory.reserved_quantity == 0
    assert ledger_count == 0


@pytest.mark.asyncio
async def test_duplicate_sku_code_rejected(api_client) -> None:
    category = await create_category(api_client)
    first_product = await create_product(api_client, category["id"])
    second_product = await create_product(api_client, category["id"])
    sku_code = new_sku_code()

    await create_sku(
        api_client,
        first_product["id"],
        sku_code=sku_code,
    )

    response = await api_client.post(
        f"/api/v1/admin/products/{second_product['id']}/skus",
        json={
            "sku_code": sku_code,
            "attributes": {"color": "blue"},
            "price": "9.99",
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "SKU_CODE_CONFLICT"


@pytest.mark.asyncio
async def test_duplicate_attributes_and_normalization(api_client) -> None:
    category = await create_category(api_client)
    product = await create_product(api_client, category["id"])

    sku = await create_sku(
        api_client,
        product["id"],
        attributes={" Color ": " Red "},
    )

    async with AsyncSessionLocal() as session:
        stored = (
            await session.execute(select(Sku).where(Sku.id == sku["id"]))
        ).scalar_one()

    assert stored.attributes == {"color": "Red"}
    assert len(stored.attributes_hash) == 64

    normalized_duplicate = await api_client.post(
        f"/api/v1/admin/products/{product['id']}/skus",
        json={
            "sku_code": new_sku_code(),
            "attributes": {"color": "Red"},
            "price": "9.99",
        },
    )
    assert normalized_duplicate.status_code == 409
    assert normalized_duplicate.json()["code"] == "SKU_ATTRIBUTES_CONFLICT"


@pytest.mark.asyncio
async def test_same_attributes_allowed_for_different_products(
    api_client,
) -> None:
    category = await create_category(api_client)
    first_product = await create_product(api_client, category["id"])
    second_product = await create_product(api_client, category["id"])

    first = await create_sku(
        api_client,
        first_product["id"],
        attributes={"color": "red"},
    )
    second = await create_sku(
        api_client,
        second_product["id"],
        attributes={"color": "red"},
    )

    assert first["id"] != second["id"]


@pytest.mark.asyncio
async def test_sku_price_must_be_positive(api_client) -> None:
    category = await create_category(api_client)
    product = await create_product(api_client, category["id"])

    response = await api_client.post(
        f"/api/v1/admin/products/{product['id']}/skus",
        json={
            "sku_code": new_sku_code(),
            "attributes": {"color": "red"},
            "price": "0",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_PRICE"


@pytest.mark.asyncio
async def test_sku_list_and_update(api_client) -> None:
    category = await create_category(api_client)
    product = await create_product(api_client, category["id"])
    sku = await create_sku(api_client, product["id"])

    listed = await api_client.get(f"/api/v1/admin/products/{product['id']}/skus")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [sku["id"]]

    updated = await api_client.patch(
        f"/api/v1/admin/skus/{sku['id']}",
        json={"price": "12.50", "status": "INACTIVE"},
    )
    assert updated.status_code == 200
    assert updated.json()["price"] == "12.50"
    assert updated.json()["status"] == "INACTIVE"

    zero_price = await api_client.patch(
        f"/api/v1/admin/skus/{sku['id']}",
        json={"price": "0"},
    )
    assert zero_price.status_code == 422
    assert zero_price.json()["code"] == "INVALID_PRICE"


@pytest.mark.asyncio
async def test_sku_update_under_archived_product_rejected(api_client) -> None:
    category = await create_category(api_client)
    product = await create_product(api_client, category["id"])
    sku = await create_sku(api_client, product["id"])

    archive = await api_client.post(f"/api/v1/admin/products/{product['id']}/archive")
    assert archive.status_code == 200

    response = await api_client.patch(
        f"/api/v1/admin/skus/{sku['id']}",
        json={"price": "12.50"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "PRODUCT_ARCHIVED"


@pytest.mark.asyncio
async def test_sku_attributes_cannot_be_updated(api_client) -> None:
    category = await create_category(api_client)
    product = await create_product(api_client, category["id"])
    sku = await create_sku(api_client, product["id"])

    response = await api_client.patch(
        f"/api/v1/admin/skus/{sku['id']}",
        json={"attributes": {"color": "blue"}},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_sku_create_on_archived_product_rejected(api_client) -> None:
    category = await create_category(api_client)
    product = await create_product(api_client, category["id"])

    archive = await api_client.post(f"/api/v1/admin/products/{product['id']}/archive")
    assert archive.status_code == 200

    response = await api_client.post(
        f"/api/v1/admin/products/{product['id']}/skus",
        json={
            "sku_code": new_sku_code(),
            "attributes": {"color": "red"},
            "price": "9.99",
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "PRODUCT_ARCHIVED"


@pytest.mark.asyncio
async def test_nested_product_creation_rolls_back_on_duplicate_sku(
    api_client,
) -> None:
    category = await create_category(api_client)
    product_no = new_product_no()

    response = await api_client.post(
        "/api/v1/admin/products",
        json={
            "product_no": product_no,
            "category_id": category["id"],
            "name": "Nested Duplicate",
            "skus": [
                {
                    "sku_code": new_sku_code(),
                    "attributes": {"color": "red"},
                    "price": "9.99",
                },
                {
                    "sku_code": new_sku_code(),
                    "attributes": {"color": "red"},
                    "price": "10.00",
                },
            ],
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "SKU_ATTRIBUTES_CONFLICT"

    async with AsyncSessionLocal() as session:
        product = (
            await session.execute(
                select(Product).where(Product.product_no == product_no)
            )
        ).scalar_one_or_none()

    assert product is None


@pytest.mark.asyncio
async def test_sku_create_failure_leaves_no_inventory(api_client) -> None:
    category = await create_category(api_client)
    product = await create_product(api_client, category["id"])
    await create_sku(
        api_client,
        product["id"],
        attributes={"color": "red"},
    )

    response = await api_client.post(
        f"/api/v1/admin/products/{product['id']}/skus",
        json={
            "sku_code": new_sku_code(),
            "attributes": {"color": "red"},
            "price": "9.99",
        },
    )
    assert response.status_code == 409

    async with AsyncSessionLocal() as session:
        inventory_count = (
            await session.execute(
                select(func.count(Inventory.id)).where(
                    Inventory.sku_id.in_(
                        select(Sku.id).where(Sku.product_id == product["id"])
                    )
                )
            )
        ).scalar_one()

    assert inventory_count == 1


@pytest.mark.asyncio
async def test_attributes_hash_cannot_be_supplied(api_client) -> None:
    category = await create_category(api_client)
    product = await create_product(api_client, category["id"])

    response = await api_client.post(
        f"/api/v1/admin/products/{product['id']}/skus",
        json={
            "sku_code": new_sku_code(),
            "attributes": {"color": "red"},
            "price": "9.99",
            "attributes_hash": "a" * 64,
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_raw_duplicate_json_keys_rejected(api_client) -> None:
    category = await create_category(api_client)
    product = await create_product(api_client, category["id"])
    payload = (
        '{"sku_code":"'
        + new_sku_code()
        + '","attributes":{"color":"red","color":"blue"},'
        '"price":"9.99"}'
    )

    response = await api_client.post(
        f"/api/v1/admin/products/{product['id']}/skus",
        content=payload,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "SKU_ATTRIBUTES_INVALID"


@pytest.mark.asyncio
async def test_missing_product_and_sku_return_404(api_client) -> None:
    product_response = await api_client.get("/api/v1/admin/products/999999999")
    assert product_response.status_code == 404
    assert product_response.json()["code"] == "PRODUCT_NOT_FOUND"

    sku_response = await api_client.post(
        "/api/v1/admin/products/999999999/skus",
        json={
            "sku_code": new_sku_code(),
            "attributes": {"color": "red"},
            "price": "9.99",
        },
    )
    assert sku_response.status_code == 404
    assert sku_response.json()["code"] == "PRODUCT_NOT_FOUND"

    update_response = await api_client.patch(
        "/api/v1/admin/skus/999999999",
        json={"price": "12.50"},
    )
    assert update_response.status_code == 404
    assert update_response.json()["code"] == "SKU_NOT_FOUND"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/admin/products",
        "/api/v1/admin/products/999999999",
        "/api/v1/admin/products/999999999/skus",
    ],
)
async def test_regular_user_gets_403_on_product_get(
    api_client,
    path: str,
) -> None:
    install_user(REGULAR_USER)

    response = await api_client.get(path)

    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/admin/products",
        "/api/v1/admin/products/999999999",
        "/api/v1/admin/products/999999999/skus",
    ],
)
async def test_anonymous_user_gets_401_on_product_get(
    api_client,
    path: str,
) -> None:
    app.dependency_overrides.pop(get_current_user, None)

    response = await api_client.get(path)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_product_status_cannot_be_patched(api_client) -> None:
    category = await create_category(api_client)
    product = await create_product(api_client, category["id"])

    response = await api_client.patch(
        f"/api/v1/admin/products/{product['id']}",
        json={"status": "ACTIVE"},
    )

    assert response.status_code == 422
