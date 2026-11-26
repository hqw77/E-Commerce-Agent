"""Agent Tool 注册工厂.

文件职责:
- 把商品, 订单, 售后和库存 Tool 注册到白名单.
- 为每个 Tool 绑定参数 Schema 和 READ/PREPARE 类型.
- 暴露进程级 TOOL_REGISTRY.

核心边界:
这里只注册能力; 是否允许调用由 Runtime 路由和 ToolExecutor 决定.
"""

from __future__ import annotations

from agent.tools.inventory import prepare_adjust_inventory
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
    PrepareAdjustInventoryInput,
    PrepareCancelOrderInput,
    PrepareCreateAfterSaleInput,
    SearchProductsInput,
)


def build_tool_registry() -> ToolRegistry:
    """构造完整的 Tool 白名单."""
    registry = ToolRegistry()
    # READ: 只读查询, 不改变业务状态.
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
    # PREPARE: 只生成用户确认或管理员审批计划.
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
    registry.register(
        RegisteredTool(
            name="prepare_adjust_inventory",
            description=(
                "Prepare an administrator-approved inventory adjustment. "
                "This only creates a pending approval and never changes stock."
            ),
            args_schema=PrepareAdjustInventoryInput,
            kind="PREPARE",
            handler=prepare_adjust_inventory,
        )
    )
    return registry


# 进程级只读注册表, 导入时构建一次.
TOOL_REGISTRY = build_tool_registry()
