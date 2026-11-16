from app.db.base import Base
from app.models import (
    AfterSale,
    Order,
    OrderItem,
    Payment,
    Refund,
)

EXPECTED_TABLES = {
    "orders",
    "order_items",
    "payments",
    "after_sales",
    "refunds",
}


def test_order_tables_are_registered() -> None:
    assert EXPECTED_TABLES <= set(Base.metadata.tables)


def test_order_table_column_counts() -> None:
    assert len(Order.__table__.columns) == 29
    assert len(OrderItem.__table__.columns) == 13
    assert len(Payment.__table__.columns) == 16
    assert len(AfterSale.__table__.columns) == 29
    assert len(Refund.__table__.columns) == 18


def test_order_constraint_and_index_names() -> None:
    expected = {
        "orders": {
            "checks": {
                "ck_orders_total_amount",
                "ck_orders_paid_amount",
                "ck_orders_refunded_amount",
                "ck_orders_fulfillment_status",
                "ck_orders_shipping_pair",
            },
            "uniques": {
                "uq_orders_order_no",
                "uq_orders_user_idempotency",
            },
            "indexes": {
                "ix_orders_user_created",
                "ix_orders_status_expires",
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
        "payments": {
            "checks": {
                "ck_payments_amount",
                "ck_payments_refunded_amount",
            },
            "uniques": {
                "uq_payments_payment_no",
                "uq_payments_order_id",
                "uq_payments_channel_trade_no",
            },
            "indexes": {
                "ix_payments_order_status",
                "ix_payments_status_created",
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
        "refunds": {
            "checks": {"ck_refunds_amount"},
            "uniques": {
                "uq_refunds_refund_no",
                "uq_refunds_payment_idempotency",
                "uq_refunds_after_sales_id",
            },
            "indexes": {
                "ix_refunds_order_status",
                "ix_refunds_payment_status",
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
        "payments": {
            "fk_payments_order",
            "fk_payments_user",
        },
        "after_sales": {
            "fk_after_sales_order",
            "fk_after_sales_order_item",
            "fk_after_sales_user",
            "fk_after_sales_reviewer",
            "fk_after_sales_receiver",
        },
        "refunds": {
            "fk_refunds_order",
            "fk_refunds_payment",
            "fk_refunds_after_sales",
            "fk_refunds_user",
        },
    }

    for table_name, names in expected.items():
        table = Base.metadata.tables[table_name]
        assert {fk.constraint.name for fk in table.foreign_keys} == names


def test_order_relationships() -> None:
    assert Order.items.property.mapper.class_ is OrderItem
    assert Order.payment.property.mapper.class_ is Payment
    assert Order.payment.property.uselist is False
    assert Order.after_sales.property.mapper.class_ is AfterSale
    assert Order.refunds.property.mapper.class_ is Refund

    assert OrderItem.order.property.mapper.class_ is Order
    assert Payment.order.property.mapper.class_ is Order
    assert Payment.refunds.property.mapper.class_ is Refund
    assert AfterSale.order.property.mapper.class_ is Order
    assert AfterSale.order_item.property.mapper.class_ is OrderItem
    assert AfterSale.refund.property.mapper.class_ is Refund
    assert AfterSale.refund.property.uselist is False
    assert Refund.payment.property.mapper.class_ is Payment
    assert Refund.after_sale.property.mapper.class_ is AfterSale


def test_order_model_nullability() -> None:
    assert Order.request_fingerprint.nullable is False
    assert Order.expires_at.nullable is False
    assert Order.shipping_carrier.nullable is True
    assert Order.tracking_no.nullable is True

    assert Payment.provider_trade_no.nullable is True
    assert Payment.paid_at.nullable is True

    assert AfterSale.approved_amount.nullable is True
    assert AfterSale.reviewed_by.nullable is True
    assert AfterSale.received_by.nullable is True

    assert Refund.after_sales_id.nullable is True
    assert Refund.processed_at.nullable is True
