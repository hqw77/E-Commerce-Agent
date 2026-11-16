from app.db.base import Base
from app.models import (
    Category,
    Inventory,
    InventoryTransaction,
    Product,
    Sku,
    User,
)

EXPECTED_TABLES = {
    "categories",
    "products",
    "skus",
    "inventory",
    "inventory_transactions",
}


def test_product_tables_are_registered() -> None:
    assert EXPECTED_TABLES <= set(Base.metadata.tables)


def test_table_column_counts() -> None:
    assert len(Category.__table__.columns) == 7
    assert len(Product.__table__.columns) == 10
    assert len(Sku.__table__.columns) == 9
    assert len(Inventory.__table__.columns) == 6
    assert len(InventoryTransaction.__table__.columns) == 14


def test_constraint_and_index_names() -> None:
    expected = {
        "categories": {
            "checks": {"ck_categories_status"},
            "uniques": set(),
            "indexes": {"ix_categories_parent_sort"},
        },
        "products": {
            "checks": {"ck_products_status", "ck_products_lifecycle"},
            "uniques": {"uq_products_product_no"},
            "indexes": {
                "ix_products_category_id",
                "ix_products_status_category",
            },
        },
        "skus": {
            "checks": {"ck_skus_price", "ck_skus_status"},
            "uniques": {
                "uq_skus_sku_code",
                "uq_skus_product_attributes",
            },
            "indexes": {"ix_skus_product_status"},
        },
        "inventory": {
            "checks": {
                "ck_inventory_total_non_negative",
                "ck_inventory_reserved_non_negative",
                "ck_inventory_reserved_le_total",
            },
            "uniques": {"uq_inventory_sku_id"},
            "indexes": set(),
        },
        "inventory_transactions": {
            "checks": {
                "ck_inventory_transactions_transaction_type",
                "ck_inventory_transactions_total_after",
                "ck_inventory_transactions_reserved_after",
                "ck_inventory_transactions_reserved_le_total",
                "ck_inventory_transactions_delta_non_zero",
            },
            "uniques": {"uq_inventory_transactions_idempotency"},
            "indexes": {
                "ix_inventory_transactions_sku_id",
                "ix_inventory_transactions_business",
            },
        },
    }

    for table_name, names in expected.items():
        table = Base.metadata.tables[table_name]
        checks = {
            constraint.name
            for constraint in table.constraints
            if constraint.__class__.__name__ == "CheckConstraint"
        }
        uniques = {
            constraint.name
            for constraint in table.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        }
        indexes = {index.name for index in table.indexes}

        assert checks == names["checks"]
        assert uniques == names["uniques"]
        assert indexes == names["indexes"]


def test_foreign_key_names() -> None:
    expected = {
        "categories": {"fk_categories_parent"},
        "products": {"fk_products_category"},
        "skus": {"fk_skus_product"},
        "inventory": {"fk_inventory_sku"},
        "inventory_transactions": {
            "fk_inventory_transactions_sku",
            "fk_inventory_transactions_operator",
        },
    }

    for table_name, names in expected.items():
        table = Base.metadata.tables[table_name]
        assert {fk.constraint.name for fk in table.foreign_keys} == names


def test_user_admin_flag_default() -> None:
    column = User.__table__.c.is_admin

    assert column.nullable is False
    assert column.server_default is not None


def test_business_item_id_is_nullable() -> None:
    column = InventoryTransaction.__table__.c.business_item_id

    assert column.nullable is True


def test_product_sku_relationships() -> None:
    assert Product.skus.property.mapper.class_ is Sku
    assert Sku.product.property.mapper.class_ is Product
