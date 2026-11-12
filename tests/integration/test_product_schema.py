from decimal import Decimal
from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.db.session import AsyncSessionLocal
from app.models import (
    Category,
    Inventory,
    InventoryTransaction,
    Product,
    Sku,
    User,
)


def _code(prefix: str) -> str:
    return f"{prefix}{uuid4().hex[:12].upper()}"


def _hash() -> str:
    return sha256(uuid4().hex.encode("utf-8")).hexdigest()


async def _create_category(session) -> Category:
    category = Category(name=f"cat-{uuid4().hex[:8]}")
    session.add(category)
    await session.flush()
    return category


async def _create_product(session, category: Category) -> Product:
    product = Product(
        product_no=_code("P"),
        category_id=category.id,
        name="Test Product",
    )
    session.add(product)
    await session.flush()
    return product


async def _create_sku(session, product: Product) -> Sku:
    sku = Sku(
        product_id=product.id,
        sku_code=_code("S"),
        attributes={"color": "red"},
        attributes_hash=_hash(),
        price=Decimal("9.99"),
    )
    session.add(sku)
    await session.flush()
    return sku


async def _create_inventory(session, sku: Sku) -> Inventory:
    inventory = Inventory(sku_id=sku.id)
    session.add(inventory)
    await session.flush()
    return inventory


async def _create_graph(session):
    category = await _create_category(session)
    product = await _create_product(session, category)
    sku = await _create_sku(session, product)
    inventory = await _create_inventory(session, sku)
    return category, product, sku, inventory


@pytest.mark.asyncio
async def test_users_is_admin_defaults_to_false() -> None:
    email = f"{uuid4().hex}@example.com"

    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                "INSERT INTO users (email, password_hash, is_active) "
                "VALUES (:email, :password_hash, :is_active)"
            ),
            {
                "email": email,
                "password_hash": "hashed-password",
                "is_active": True,
            },
        )

        value = (
            await session.execute(select(User.is_admin).where(User.email == email))
        ).scalar_one()

        assert value is False
        await session.rollback()


@pytest.mark.asyncio
async def test_duplicate_product_no_rejected() -> None:
    async with AsyncSessionLocal() as session:
        category = await _create_category(session)
        product = await _create_product(session, category)

        session.add(
            Product(
                product_no=product.product_no,
                category_id=category.id,
                name="Duplicate Product",
            )
        )

        with pytest.raises(IntegrityError):
            await session.flush()

        await session.rollback()


@pytest.mark.asyncio
async def test_duplicate_sku_code_rejected() -> None:
    async with AsyncSessionLocal() as session:
        _category, product, sku, _inventory = await _create_graph(session)

        session.add(
            Sku(
                product_id=product.id,
                sku_code=sku.sku_code,
                attributes={"color": "blue"},
                attributes_hash=_hash(),
                price=Decimal("10.00"),
            )
        )

        with pytest.raises(IntegrityError):
            await session.flush()

        await session.rollback()


@pytest.mark.asyncio
async def test_duplicate_sku_attributes_hash_rejected() -> None:
    async with AsyncSessionLocal() as session:
        _category, product, sku, _inventory = await _create_graph(session)

        session.add(
            Sku(
                product_id=product.id,
                sku_code=_code("S"),
                attributes={"color": "blue"},
                attributes_hash=sku.attributes_hash,
                price=Decimal("10.00"),
            )
        )

        with pytest.raises(IntegrityError):
            await session.flush()

        await session.rollback()


@pytest.mark.asyncio
async def test_duplicate_inventory_sku_rejected() -> None:
    async with AsyncSessionLocal() as session:
        _category, _product, sku, _inventory = await _create_graph(session)

        session.add(Inventory(sku_id=sku.id))

        with pytest.raises(IntegrityError):
            await session.flush()

        await session.rollback()


@pytest.mark.asyncio
async def test_product_lifecycle_check_rejected() -> None:
    async with AsyncSessionLocal() as session:
        category = await _create_category(session)

        session.add(
            Product(
                product_no=_code("P"),
                category_id=category.id,
                name="Active Without Published At",
                status="ACTIVE",
            )
        )

        with pytest.raises(OperationalError) as exc_info:
            await session.flush()

        assert "ck_products_lifecycle" in str(exc_info.value)
        await session.rollback()


@pytest.mark.asyncio
async def test_product_status_check_rejected() -> None:
    async with AsyncSessionLocal() as session:
        category = await _create_category(session)

        session.add(
            Product(
                product_no=_code("P"),
                category_id=category.id,
                name="Invalid Status",
                status="UNKNOWN",
            )
        )

        with pytest.raises(OperationalError) as exc_info:
            await session.flush()

        assert "ck_products" in str(exc_info.value)
        await session.rollback()


@pytest.mark.asyncio
async def test_sku_price_and_status_checks_rejected() -> None:
    async with AsyncSessionLocal() as session:
        _category, product, _sku, _inventory = await _create_graph(session)

        session.add(
            Sku(
                product_id=product.id,
                sku_code=_code("S"),
                attributes={"color": "blue"},
                attributes_hash=_hash(),
                price=Decimal(0),
            )
        )

        with pytest.raises(OperationalError) as exc_info:
            await session.flush()

        assert "ck_skus_price" in str(exc_info.value)
        await session.rollback()

    async with AsyncSessionLocal() as session:
        _category, product, _sku, _inventory = await _create_graph(session)

        session.add(
            Sku(
                product_id=product.id,
                sku_code=_code("S"),
                attributes={"color": "blue"},
                attributes_hash=_hash(),
                price=Decimal("10.00"),
                status="UNKNOWN",
            )
        )

        with pytest.raises(OperationalError) as exc_info:
            await session.flush()

        assert "ck_skus_status" in str(exc_info.value)
        await session.rollback()


@pytest.mark.asyncio
async def test_inventory_checks_rejected() -> None:
    async with AsyncSessionLocal() as session:
        _category, _product, _sku, inventory = await _create_graph(session)

        inventory.total_quantity = -1
        inventory.reserved_quantity = -1

        with pytest.raises(OperationalError) as exc_info:
            await session.flush()

        assert "ck_inventory_" in str(exc_info.value)
        await session.rollback()

    async with AsyncSessionLocal() as session:
        _category, _product, _sku, inventory = await _create_graph(session)

        inventory.total_quantity = 1
        inventory.reserved_quantity = 2

        with pytest.raises(OperationalError) as exc_info:
            await session.flush()

        assert "ck_inventory_reserved_le_total" in str(exc_info.value)
        await session.rollback()


@pytest.mark.asyncio
async def test_transaction_type_and_delta_checks_rejected() -> None:
    async with AsyncSessionLocal() as session:
        _category, _product, sku, _inventory = await _create_graph(session)

        session.add(
            InventoryTransaction(
                sku_id=sku.id,
                transaction_type="UNKNOWN",
                total_delta=1,
                reserved_delta=0,
                total_after=1,
                reserved_after=0,
                idempotency_key=_code("K"),
            )
        )

        with pytest.raises(OperationalError) as exc_info:
            await session.flush()

        assert "ck_inventory_transactions_transaction_type" in str(exc_info.value)
        await session.rollback()

    async with AsyncSessionLocal() as session:
        _category, _product, sku, _inventory = await _create_graph(session)

        session.add(
            InventoryTransaction(
                sku_id=sku.id,
                transaction_type="STOCK_IN",
                total_delta=0,
                reserved_delta=0,
                total_after=0,
                reserved_after=0,
                idempotency_key=_code("K"),
            )
        )

        with pytest.raises(OperationalError) as exc_info:
            await session.flush()

        assert "ck_inventory_transactions_delta_non_zero" in str(exc_info.value)
        await session.rollback()


@pytest.mark.asyncio
async def test_transaction_snapshot_checks_rejected() -> None:
    async with AsyncSessionLocal() as session:
        _category, _product, sku, _inventory = await _create_graph(session)

        session.add(
            InventoryTransaction(
                sku_id=sku.id,
                transaction_type="STOCK_IN",
                total_delta=1,
                reserved_delta=0,
                total_after=-1,
                reserved_after=-1,
                idempotency_key=_code("K"),
            )
        )

        with pytest.raises(OperationalError) as exc_info:
            await session.flush()

        assert "ck_inventory_transactions_" in str(exc_info.value)
        await session.rollback()

    async with AsyncSessionLocal() as session:
        _category, _product, sku, _inventory = await _create_graph(session)

        session.add(
            InventoryTransaction(
                sku_id=sku.id,
                transaction_type="RESERVE",
                total_delta=0,
                reserved_delta=2,
                total_after=1,
                reserved_after=2,
                idempotency_key=_code("K"),
            )
        )

        with pytest.raises(OperationalError) as exc_info:
            await session.flush()

        assert "ck_inventory_transactions_reserved_le_total" in str(exc_info.value)
        await session.rollback()


@pytest.mark.asyncio
async def test_duplicate_idempotency_key_rejected() -> None:
    async with AsyncSessionLocal() as session:
        _category, _product, sku, _inventory = await _create_graph(session)
        key = _code("K")

        for _ in range(2):
            session.add(
                InventoryTransaction(
                    sku_id=sku.id,
                    transaction_type="STOCK_IN",
                    total_delta=1,
                    reserved_delta=0,
                    total_after=1,
                    reserved_after=0,
                    idempotency_key=key,
                )
            )

        with pytest.raises(IntegrityError):
            await session.flush()

        await session.rollback()


@pytest.mark.asyncio
async def test_foreign_key_constraints_rejected() -> None:
    async with AsyncSessionLocal() as session:
        session.add(
            Category(
                name="Invalid Parent",
                parent_id=999_999_999,
            )
        )

        with pytest.raises(IntegrityError):
            await session.flush()

        await session.rollback()

    async with AsyncSessionLocal() as session:
        session.add(
            Product(
                product_no=_code("P"),
                category_id=999_999_999,
                name="Invalid Category",
            )
        )

        with pytest.raises(IntegrityError):
            await session.flush()

        await session.rollback()

    async with AsyncSessionLocal() as session:
        session.add(
            Sku(
                product_id=999_999_999,
                sku_code=_code("S"),
                attributes={"color": "red"},
                attributes_hash=_hash(),
                price=Decimal("9.99"),
            )
        )

        with pytest.raises(IntegrityError):
            await session.flush()

        await session.rollback()

    async with AsyncSessionLocal() as session:
        session.add(Inventory(sku_id=999_999_999))

        with pytest.raises(IntegrityError):
            await session.flush()

        await session.rollback()

    async with AsyncSessionLocal() as session:
        session.add(
            InventoryTransaction(
                sku_id=999_999_999,
                transaction_type="STOCK_IN",
                total_delta=1,
                reserved_delta=0,
                total_after=1,
                reserved_after=0,
                idempotency_key=_code("K"),
            )
        )

        with pytest.raises(IntegrityError):
            await session.flush()

        await session.rollback()
