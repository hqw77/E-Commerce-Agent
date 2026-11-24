"""Tool registry factory for TASK-007."""

from __future__ import annotations

from agent.tools.order import (
    get_my_after_sales,
    get_my_order,
    list_my_after_sales,
    list_my_orders,
    prepare_cancel_order,
    prepare_create_after_sales,
)
from agent.tools.product import (
    check_sku_inventory,
    get_product_detail,
    get_sku_detail,
    search_products,
)
from agent.tools.registry import RegisteredTool, ToolRegistry
from agent.tools.schemas import (
    CheckSkuInventoryInput,
    GetMyAfterSalesInput,
    GetMyOrderInput,
    GetProductDetailInput,
    GetSkuDetailInput,
    ListMyAfterSalesInput,
    ListMyOrdersInput,
    PrepareCancelOrderInput,
    PrepareCreateAfterSaleInput,
    SearchProductsInput,
)


def build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        RegisteredTool(
            name="search_products",
            description="Search active products by keyword.",
            args_schema=SearchProductsInput,
            kind="READ",
            handler=search_products,
        )
    )
    registry.register(
        RegisteredTool(
            name="get_product_detail",
            description="Get one active product by product_no.",
            args_schema=GetProductDetailInput,
            kind="READ",
            handler=get_product_detail,
        )
    )
    registry.register(
        RegisteredTool(
            name="get_sku_detail",
            description="Get one active SKU by sku_code.",
            args_schema=GetSkuDetailInput,
            kind="READ",
            handler=get_sku_detail,
        )
    )
    registry.register(
        RegisteredTool(
            name="check_sku_inventory",
            description="Check available inventory by sku_code.",
            args_schema=CheckSkuInventoryInput,
            kind="READ",
            handler=check_sku_inventory,
        )
    )
    registry.register(
        RegisteredTool(
            name="list_my_orders",
            description="List orders belonging to the authenticated user.",
            args_schema=ListMyOrdersInput,
            kind="READ",
            handler=list_my_orders,
        )
    )
    registry.register(
        RegisteredTool(
            name="get_my_order",
            description="Get one order belonging to the authenticated user.",
            args_schema=GetMyOrderInput,
            kind="READ",
            handler=get_my_order,
        )
    )
    registry.register(
        RegisteredTool(
            name="list_my_after_sales",
            description="List after-sales records for the authenticated user.",
            args_schema=ListMyAfterSalesInput,
            kind="READ",
            handler=list_my_after_sales,
        )
    )
    registry.register(
        RegisteredTool(
            name="get_my_after_sales",
            description="Get one after-sales record for the authenticated user.",
            args_schema=GetMyAfterSalesInput,
            kind="READ",
            handler=get_my_after_sales,
        )
    )
    registry.register(
        RegisteredTool(
            name="prepare_cancel_order",
            description=(
                "Prepare cancellation of an unshipped CREATED order for explicit "
                "user confirmation. This does not cancel the order."
            ),
            args_schema=PrepareCancelOrderInput,
            kind="PREPARE",
            handler=prepare_cancel_order,
        )
    )
    registry.register(
        RegisteredTool(
            name="prepare_create_after_sales",
            description=(
                "Prepare an after-sales application for explicit user "
                "confirmation. This does not create an after-sales record."
            ),
            args_schema=PrepareCreateAfterSaleInput,
            kind="PREPARE",
            handler=prepare_create_after_sales,
        )
    )
    return registry


TOOL_REGISTRY = build_tool_registry()
