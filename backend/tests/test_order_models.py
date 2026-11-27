from app.db.base import Base
from app.models import AfterSale, Order, OrderItem

EXPECTED_TABLES = {
    "orders",
    "order_items",
    "after_sales",
}


def test_order_tables_are_registered() -> None:
    assert EXPECTED_TABLES <= set(Base.metadata.tables)


def test_legacy_payment_tables_are_removed() -> None:
    assert "payments" not in Base.metadata.tables
    assert "refunds" not in Base.metadata.tables


def test_order_table_column_counts() -> None:
    assert len(Order.__table__.columns) == 24
    assert len(OrderItem.__table__.columns) == 13
    assert len(AfterSale.__table__.columns) == 29


def test_order_constraint_and_index_names() -> None:
    expected = {
        "orders": {
            "checks": {
                "ck_orders_total_amount",
                "ck_orders_fulfillment_status",
                "ck_orders_shipping_pair",
            },
            "uniques": {
                "uq_orders_order_no",
                "uq_orders_user_idempotency",
            },
            "indexes": {
                "ix_orders_user_created",
                "ix_orders_created_at",
                "ix_orders_tracking_no",
            },
        },
        "order_items": {
            "checks": {
                "ck_order_items_quantity",
                "ck_order_items_unit_price",
                "ck_order_items_line_amount",
            },
            "uniques": {"uq_order_items_order_sku"},
            "indexes": {
                "ix_order_items_sku_id",
                "ix_order_items_product_id",
            },
        },
        "after_sales": {
            "checks": {
                "ck_after_sales_quantity",
                "ck_after_sales_requested_amount",
                "ck_after_sales_approved_amount",
            },
            "uniques": {
                "uq_after_sales_after_sales_no",
                "uq_after_sales_user_idempotency",
            },
            "indexes": {
                "ix_after_sales_user_status",
                "ix_after_sales_order_id",
                "ix_after_sales_order_item_status",
                "ix_after_sales_status_created",
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


def test_order_foreign_key_names() -> None:
    expected = {
        "orders": {"fk_orders_user"},
        "order_items": {
            "fk_order_items_order",
            "fk_order_items_product",
            "fk_order_items_sku",
        },
        "after_sales": {
            "fk_after_sales_order",
            "fk_after_sales_order_item",
            "fk_after_sales_user",
            "fk_after_sales_reviewer",
            "fk_after_sales_receiver",
        },
    }

    for table_name, names in expected.items():
        table = Base.metadata.tables[table_name]
        assert {fk.constraint.name for fk in table.foreign_keys} == names


def test_order_relationships() -> None:
    assert Order.items.property.mapper.class_ is OrderItem
    assert Order.after_sales.property.mapper.class_ is AfterSale

    assert OrderItem.order.property.mapper.class_ is Order
    assert AfterSale.order.property.mapper.class_ is Order
    assert AfterSale.order_item.property.mapper.class_ is OrderItem


def test_order_model_nullability() -> None:
    assert Order.request_fingerprint.nullable is False
    assert Order.shipping_carrier.nullable is True
    assert Order.tracking_no.nullable is True

    assert AfterSale.approved_amount.nullable is True
    assert AfterSale.reviewed_by.nullable is True
    assert AfterSale.received_by.nullable is True
