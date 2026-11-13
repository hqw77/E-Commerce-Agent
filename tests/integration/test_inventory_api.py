import asyncio
from types import SimpleNamespace
from typing import Annotated
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import AsyncSessionLocal, get_db
from app.main import app
from app.models.category import Category
from app.models.inventory import Inventory
from app.models.inventory_transaction import InventoryTransaction
from app.models.product import Product
from app.models.sku import Sku
from app.models.user import User
from app.services.inventory import InventoryService

CATEGORY_PREFIX = "inv-cat-"
PRODUCT_PREFIX = "INVP"
SKU_PREFIX = "INVS"
EMAIL_PREFIX = "inv-admin-"


def install_user(user: SimpleNamespace) -> None:
    async def fake_current_user(
        session: Annotated[AsyncSession, Depends(get_db)],
    ) -> SimpleNamespace:
        await session.execute(text("SELECT 1"))
        return user

    app.dependency_overrides[get_current_user] = fake_current_user


def new_key() -> str:
    return f"inv-key-{uuid4().hex}"


def new_sku_code() -> str:
    return f"{SKU_PREFIX}{uuid4().hex[:12].upper()}"


@pytest_asyncio.fixture
async def api_client():
    async with AsyncSessionLocal() as session:
        admin = User(
            email=f"{EMAIL_PREFIX}{uuid4().hex[:8]}@example.com",
            password_hash="hashed-password",
            is_active=True,
            is_admin=True,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        admin_id = admin.id

    admin_user = SimpleNamespace(
        id=admin_id,
        email=admin.email,
        is_active=True,
        is_admin=True,
    )

    async def override_get_db():
        async with AsyncSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    install_user(admin_user)

    transport = ASGITransport(app=app)

    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            yield client, admin_user
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

                ids = {row.id for row in rows}
                parent_ids = {row.parent_id for row in rows if row.parent_id in ids}
                leaves = [item for item in ids if item not in parent_ids]

                if not leaves:
                    break

                await session.execute(delete(Category).where(Category.id.in_(leaves)))

            await session.execute(
                delete(User).where(User.email.like(f"{EMAIL_PREFIX}%"))
            )
            await session.commit()


async def create_sku(client: AsyncClient) -> dict:
    category = await client.post(
        "/api/v1/admin/categories",
        json={"name": f"{CATEGORY_PREFIX}{uuid4().hex[:8]}"},
    )
    assert category.status_code == 201, category.text

    product = await client.post(
        "/api/v1/admin/products",
        json={
            "product_no": f"{PRODUCT_PREFIX}{uuid4().hex[:12].upper()}",
            "category_id": category.json()["id"],
            "name": "Inventory Product",
        },
    )
    assert product.status_code == 201, product.text

    sku = await client.post(
        f"/api/v1/admin/products/{product.json()['id']}/skus",
        json={
            "sku_code": new_sku_code(),
            "attributes": {"color": "red"},
            "price": "9.99",
        },
    )
    assert sku.status_code == 201, sku.text
    return sku.json()


async def initialize(
    client: AsyncClient,
    sku_id: int,
    total: int = 10,
    *,
    key: str | None = None,
) -> dict:
    response = await client.post(
        f"/api/v1/admin/inventory/{sku_id}/initialize",
        json={
            "initial_total": total,
            "idempotency_key": key or new_key(),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def inventory_state(
    sku_id: int,
) -> tuple[Inventory | None, list[InventoryTransaction]]:
    async with AsyncSessionLocal() as session:
        inventory = (
            await session.execute(select(Inventory).where(Inventory.sku_id == sku_id))
        ).scalar_one_or_none()
        transactions = list(
            (
                await session.execute(
                    select(InventoryTransaction)
                    .where(InventoryTransaction.sku_id == sku_id)
                    .order_by(InventoryTransaction.id)
                )
            ).scalars()
        )
        return inventory, transactions


async def set_reserved(sku_id: int, reserved: int) -> None:
    async with AsyncSessionLocal() as session:
        inventory = (
            await session.execute(select(Inventory).where(Inventory.sku_id == sku_id))
        ).scalar_one()
        inventory.reserved_quantity = reserved
        await session.commit()


@pytest.mark.asyncio
async def test_initialize_inventory(api_client) -> None:
    client, admin = api_client
    sku = await create_sku(client)

    response = await client.post(
        f"/api/v1/admin/inventory/{sku['id']}/initialize",
        json={
            "initial_total": 10,
            "idempotency_key": new_key(),
            "remark": "initial import",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["inventory"] == {
        "sku_id": sku["id"],
        "total_quantity": 10,
        "reserved_quantity": 0,
        "available_quantity": 10,
    }
    assert body["transaction"]["transaction_type"] == "INITIAL"
    assert body["transaction"]["total_delta"] == 10
    assert body["transaction"]["total_after"] == 10
    assert body["transaction"]["operator_id"] == admin.id

    inventory, transactions = await inventory_state(sku["id"])
    assert inventory is not None
    assert len(transactions) == 1
    assert transactions[0].transaction_type == "INITIAL"


@pytest.mark.asyncio
async def test_initialize_rejects_invalid_and_missing(api_client) -> None:
    client, _admin = api_client
    sku = await create_sku(client)

    zero = await client.post(
        f"/api/v1/admin/inventory/{sku['id']}/initialize",
        json={"initial_total": 0, "idempotency_key": new_key()},
    )
    assert zero.status_code == 422
    assert zero.json()["code"] == "INVALID_QUANTITY"

    missing = await client.post(
        "/api/v1/admin/inventory/999999999/initialize",
        json={"initial_total": 10, "idempotency_key": new_key()},
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "INVENTORY_NOT_FOUND"


@pytest.mark.asyncio
async def test_initialize_twice_rejected(api_client) -> None:
    client, _admin = api_client
    sku = await create_sku(client)
    await initialize(client, sku["id"], 10)

    response = await client.post(
        f"/api/v1/admin/inventory/{sku['id']}/initialize",
        json={"initial_total": 5, "idempotency_key": new_key()},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "INVENTORY_ALREADY_INITIALIZED"

    inventory, transactions = await inventory_state(sku["id"])
    assert inventory is not None
    assert inventory.total_quantity == 10
    assert len(transactions) == 1


@pytest.mark.asyncio
async def test_stock_in_and_idempotency(api_client) -> None:
    client, _admin = api_client
    sku = await create_sku(client)
    await initialize(client, sku["id"], 10)
    key = new_key()

    response = await client.post(
        f"/api/v1/admin/inventory/{sku['id']}/stock-in",
        json={"quantity": 5, "idempotency_key": key},
    )
    assert response.status_code == 200
    assert response.json()["inventory"]["total_quantity"] == 15

    repeat = await client.post(
        f"/api/v1/admin/inventory/{sku['id']}/stock-in",
        json={"quantity": 5, "idempotency_key": key},
    )
    assert repeat.status_code == 200
    assert repeat.json()["inventory"]["total_quantity"] == 15

    conflict = await client.post(
        f"/api/v1/admin/inventory/{sku['id']}/stock-in",
        json={"quantity": 6, "idempotency_key": key},
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_KEY_CONFLICT"

    inventory, transactions = await inventory_state(sku["id"])
    assert inventory is not None
    assert inventory.total_quantity == 15
    assert [item.transaction_type for item in transactions] == [
        "INITIAL",
        "STOCK_IN",
    ]
    stock_in = transactions[1]
    assert stock_in.total_delta == 5
    assert stock_in.total_after == 15
    assert stock_in.reserved_after == 0


@pytest.mark.asyncio
async def test_direct_outbound_rules(api_client) -> None:
    client, _admin = api_client
    sku = await create_sku(client)
    await initialize(client, sku["id"], 10)

    outbound = await client.post(
        f"/api/v1/admin/inventory/{sku['id']}/stock-out",
        json={"quantity": 3, "idempotency_key": new_key()},
    )
    assert outbound.status_code == 200
    assert outbound.json()["inventory"]["total_quantity"] == 7
    assert outbound.json()["inventory"]["available_quantity"] == 7

    insufficient = await client.post(
        f"/api/v1/admin/inventory/{sku['id']}/stock-out",
        json={"quantity": 100, "idempotency_key": new_key()},
    )
    assert insufficient.status_code == 409
    assert insufficient.json()["code"] == "INSUFFICIENT_STOCK"

    await set_reserved(sku["id"], 5)
    reserved_block = await client.post(
        f"/api/v1/admin/inventory/{sku['id']}/stock-out",
        json={"quantity": 3, "idempotency_key": new_key()},
    )
    assert reserved_block.status_code == 409

    allowed = await client.post(
        f"/api/v1/admin/inventory/{sku['id']}/stock-out",
        json={"quantity": 2, "idempotency_key": new_key()},
    )
    assert allowed.status_code == 200
    assert allowed.json()["inventory"]["total_quantity"] == 5
    assert allowed.json()["inventory"]["reserved_quantity"] == 5
    assert allowed.json()["inventory"]["available_quantity"] == 0

    inventory, transactions = await inventory_state(sku["id"])
    assert inventory is not None
    assert inventory.total_quantity == 5
    assert inventory.reserved_quantity == 5
    outbound_rows = [
        item for item in transactions if item.transaction_type == "DIRECT_OUTBOUND"
    ]
    assert outbound_rows[-1].total_delta == -2
    assert outbound_rows[-1].reserved_delta == 0
    assert outbound_rows[-1].total_after == 5
    assert outbound_rows[-1].reserved_after == 5


@pytest.mark.asyncio
async def test_adjustment_rules(api_client) -> None:
    client, _admin = api_client
    sku = await create_sku(client)
    await initialize(client, sku["id"], 10)

    plus = await client.post(
        f"/api/v1/admin/inventory/{sku['id']}/adjust",
        json={"quantity_delta": 5, "idempotency_key": new_key()},
    )
    assert plus.status_code == 200
    assert plus.json()["inventory"]["total_quantity"] == 15

    minus_key = new_key()
    minus = await client.post(
        f"/api/v1/admin/inventory/{sku['id']}/adjust",
        json={"quantity_delta": -3, "idempotency_key": minus_key},
    )
    assert minus.status_code == 200
    assert minus.json()["inventory"]["total_quantity"] == 12

    repeat = await client.post(
        f"/api/v1/admin/inventory/{sku['id']}/adjust",
        json={"quantity_delta": -3, "idempotency_key": minus_key},
    )
    assert repeat.status_code == 200
    assert repeat.json()["inventory"]["total_quantity"] == 12

    zero = await client.post(
        f"/api/v1/admin/inventory/{sku['id']}/adjust",
        json={"quantity_delta": 0, "idempotency_key": new_key()},
    )
    assert zero.status_code == 422
    assert zero.json()["code"] == "INVALID_QUANTITY"

    negative = await client.post(
        f"/api/v1/admin/inventory/{sku['id']}/adjust",
        json={"quantity_delta": -100, "idempotency_key": new_key()},
    )
    assert negative.status_code == 409
    assert negative.json()["code"] == "INSUFFICIENT_STOCK"

    await set_reserved(sku["id"], 5)
    below_reserved = await client.post(
        f"/api/v1/admin/inventory/{sku['id']}/adjust",
        json={"quantity_delta": -8, "idempotency_key": new_key()},
    )
    assert below_reserved.status_code == 409

    to_reserved = await client.post(
        f"/api/v1/admin/inventory/{sku['id']}/adjust",
        json={"quantity_delta": -7, "idempotency_key": new_key()},
    )
    assert to_reserved.status_code == 200
    assert to_reserved.json()["inventory"]["total_quantity"] == 5
    assert to_reserved.json()["inventory"]["reserved_quantity"] == 5

    inventory, transactions = await inventory_state(sku["id"])
    assert inventory is not None
    assert inventory.total_quantity == 5
    assert inventory.reserved_quantity == 5
    assert transactions[-1].transaction_type == "ADJUSTMENT"
    assert transactions[-1].reserved_delta == 0


@pytest.mark.asyncio
async def test_inventory_queries(api_client) -> None:
    client, _admin = api_client
    sku = await create_sku(client)
    await initialize(client, sku["id"], 10)
    await client.post(
        f"/api/v1/admin/inventory/{sku['id']}/stock-in",
        json={"quantity": 5, "idempotency_key": new_key()},
    )

    detail = await client.get(f"/api/v1/admin/inventory/{sku['id']}")
    assert detail.status_code == 200
    assert detail.json()["available_quantity"] == 15

    first_page = await client.get(
        f"/api/v1/admin/inventory/{sku['id']}/transactions",
        params={"page": 1, "page_size": 1},
    )
    assert first_page.status_code == 200
    assert first_page.json()["total"] == 2
    assert len(first_page.json()["items"]) == 1

    second_page = await client.get(
        f"/api/v1/admin/inventory/{sku['id']}/transactions",
        params={"page": 2, "page_size": 1},
    )
    assert second_page.status_code == 200
    assert len(second_page.json()["items"]) == 1

    missing = await client.get("/api/v1/admin/inventory/999999999")
    assert missing.status_code == 404
    assert missing.json()["code"] == "INVENTORY_NOT_FOUND"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/admin/inventory/999999999",
        "/api/v1/admin/inventory/999999999/transactions",
    ],
)
async def test_regular_user_gets_403_on_inventory_get(
    api_client,
    path: str,
) -> None:
    client, _admin = api_client
    install_user(
        SimpleNamespace(
            id=999,
            email="user@example.com",
            is_active=True,
            is_admin=False,
        )
    )

    response = await client.get(path)

    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_anonymous_user_gets_401_on_inventory_get(api_client) -> None:
    client, _admin = api_client
    app.dependency_overrides.pop(get_current_user, None)

    response = await client.get("/api/v1/admin/inventory/999999999")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_concurrent_stock_in_does_not_lose_updates(api_client) -> None:
    client, _admin = api_client
    sku = await create_sku(client)
    await initialize(client, sku["id"], 1)

    responses = await asyncio.gather(
        client.post(
            f"/api/v1/admin/inventory/{sku['id']}/stock-in",
            json={"quantity": 5, "idempotency_key": new_key()},
        ),
        client.post(
            f"/api/v1/admin/inventory/{sku['id']}/stock-in",
            json={"quantity": 7, "idempotency_key": new_key()},
        ),
    )

    assert [response.status_code for response in responses] == [200, 200]

    inventory, transactions = await inventory_state(sku["id"])
    assert inventory is not None
    assert inventory.total_quantity == 13
    assert (
        len([item for item in transactions if item.transaction_type == "STOCK_IN"]) == 2
    )


@pytest.mark.asyncio
async def test_concurrent_outbound_does_not_go_negative(api_client) -> None:
    client, _admin = api_client
    sku = await create_sku(client)
    await initialize(client, sku["id"], 10)

    responses = await asyncio.gather(
        client.post(
            f"/api/v1/admin/inventory/{sku['id']}/stock-out",
            json={"quantity": 7, "idempotency_key": new_key()},
        ),
        client.post(
            f"/api/v1/admin/inventory/{sku['id']}/stock-out",
            json={"quantity": 7, "idempotency_key": new_key()},
        ),
    )

    statuses = sorted(response.status_code for response in responses)
    assert statuses == [200, 409]

    inventory, transactions = await inventory_state(sku["id"])
    assert inventory is not None
    assert inventory.total_quantity == 3
    assert inventory.total_quantity >= 0
    assert (
        len(
            [
                item
                for item in transactions
                if item.transaction_type == "DIRECT_OUTBOUND"
            ]
        )
        == 1
    )


@pytest.mark.asyncio
async def test_concurrent_same_idempotency_key_executes_once(
    api_client,
) -> None:
    client, _admin = api_client
    sku = await create_sku(client)
    await initialize(client, sku["id"], 10)
    key = new_key()

    responses = await asyncio.gather(
        client.post(
            f"/api/v1/admin/inventory/{sku['id']}/stock-in",
            json={"quantity": 5, "idempotency_key": key},
        ),
        client.post(
            f"/api/v1/admin/inventory/{sku['id']}/stock-in",
            json={"quantity": 5, "idempotency_key": key},
        ),
    )

    assert [response.status_code for response in responses] == [200, 200]

    inventory, transactions = await inventory_state(sku["id"])
    assert inventory is not None
    assert inventory.total_quantity == 15
    assert len([item for item in transactions if item.idempotency_key == key]) == 1


@pytest.mark.asyncio
async def test_same_key_different_skus_rolls_back_loser(api_client) -> None:
    client, _admin = api_client
    first = await create_sku(client)
    second = await create_sku(client)
    await initialize(client, first["id"], 10)
    await initialize(client, second["id"], 10)
    key = new_key()

    responses = await asyncio.gather(
        client.post(
            f"/api/v1/admin/inventory/{first['id']}/stock-in",
            json={"quantity": 5, "idempotency_key": key},
        ),
        client.post(
            f"/api/v1/admin/inventory/{second['id']}/stock-in",
            json={"quantity": 5, "idempotency_key": key},
        ),
    )

    statuses = sorted(response.status_code for response in responses)
    assert statuses == [200, 409]

    first_inventory, _ = await inventory_state(first["id"])
    second_inventory, _ = await inventory_state(second["id"])
    assert first_inventory is not None
    assert second_inventory is not None
    assert sorted(
        [first_inventory.total_quantity, second_inventory.total_quantity]
    ) == [10, 15]

    async with AsyncSessionLocal() as session:
        ledger_count = len(
            (
                await session.execute(
                    select(InventoryTransaction).where(
                        InventoryTransaction.idempotency_key == key
                    )
                )
            )
            .scalars()
            .all()
        )
    assert ledger_count == 1


@pytest.mark.asyncio
async def test_commit_failure_rolls_back_inventory_and_ledger(
    api_client,
) -> None:
    client, admin = api_client
    sku = await create_sku(client)
    await initialize(client, sku["id"], 10)

    async with AsyncSessionLocal() as session:
        service = InventoryService(session)
        original_commit = session.commit

        async def failing_commit() -> None:
            raise RuntimeError("commit failed")

        session.commit = failing_commit  # type: ignore[method-assign]

        try:
            with pytest.raises(RuntimeError):
                await service.stock_in(
                    sku_id=sku["id"],
                    quantity=5,
                    idempotency_key=new_key(),
                    operator_id=admin.id,
                    remark=None,
                )
        finally:
            session.commit = original_commit  # type: ignore[method-assign]
            await session.rollback()

    inventory, transactions = await inventory_state(sku["id"])
    assert inventory is not None
    assert inventory.total_quantity == 10
    assert [item.transaction_type for item in transactions] == ["INITIAL"]
