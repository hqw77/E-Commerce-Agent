"""商品, SKU 和库存的只读 Agent Tool.

文件职责:
- 搜索在售商品.
- 查询商品, SKU 和可用库存.
- 把 ORM 数据转换成模型安全可读的字典.

核心边界:
全部为 READ Tool, 不修改商品或库存.
"""

from __future__ import annotations

from typing import Any

from app.services.inventory import InventoryService
from app.services.product import ProductService
from app.services.sku import SkuService
from pydantic import BaseModel

from agent.tools.context import ToolContext
from agent.tools.errors import ToolResult
from agent.tools.schemas import (
    CheckSkuInventoryInput,
    GetProductDetailInput,
    GetSkuDetailInput,
    SearchProductsInput,
)


def _decimal(value: Any) -> str:
    """把 Decimal 价格转成字符串, 避免浮点误差."""
    return str(value)


async def _find_product(
    service: ProductService,
    product_no: str,
) -> Any:
    """按商品编号读取详情, 统一处理 Service 异常."""
    return await service.get_product_detail_by_no(product_no)


async def search_products(
    context: ToolContext,
    raw_args: BaseModel,
) -> ToolResult:
    """按关键词搜索 ACTIVE 商品, 返回价格区间."""
    args = SearchProductsInput.model_validate(raw_args.model_dump())
    service = ProductService(context.session)
    result = await service.list_products(
        status="ACTIVE",
        category_id=None,
        keyword=args.query,
        page=args.page,
        page_size=args.page_size,
    )
    items: list[dict[str, Any]] = []
    # ① 列表接口不含 SKU, 逐个补充有效 SKU 的价格区间.
    for product in result.items:
        detail = await service.get_product_detail(product.id)
        prices = [sku.price for sku in detail.skus if sku.status == "ACTIVE"]
        items.append(
            {
                "product_no": detail.product_no,
                "name": detail.name,
                "description": detail.description,
                "status": detail.status,
                "price_range": (
                    {
                        "min": _decimal(min(prices)),
                        "max": _decimal(max(prices)),
                        "currency": "CNY",
                    }
                    if prices
                    else None
                ),
            }
        )
    return ToolResult(
        ok=True,
        tool="search_products",
        data={"items": items, "total": result.total, "page": result.page},
    )


async def get_product_detail(
    context: ToolContext,
    raw_args: BaseModel,
) -> ToolResult:
    """按商品编号返回商品详情和 SKU 列表."""
    args = GetProductDetailInput.model_validate(raw_args.model_dump())
    detail = await _find_product(ProductService(context.session), args.product_no)
    return ToolResult(
        ok=True,
        tool="get_product_detail",
        data={
            "product_no": detail.product_no,
            "name": detail.name,
            "description": detail.description,
            "status": detail.status,
            "skus": [
                {
                    "sku_code": sku.sku_code,
                    "attributes": sku.attributes,
                    "price": _decimal(sku.price),
                    "status": sku.status,
                    "available_quantity": (
                        sku.inventory.available_quantity
                        if sku.inventory is not None
                        else None
                    ),
                }
                for sku in detail.skus
            ],
        },
    )


async def get_sku_detail(
    context: ToolContext,
    raw_args: BaseModel,
) -> ToolResult:
    """按 SKU 编码返回规格, 价格和可用库存."""
    args = GetSkuDetailInput.model_validate(raw_args.model_dump())
    sku, product = await SkuService(context.session).get_sku_by_code(args.sku_code)
    inventory = await InventoryService(context.session).get_inventory(sku.id)
    return ToolResult(
        ok=True,
        tool="get_sku_detail",
        data={
            "sku_code": sku.sku_code,
            "product_no": product.product_no,
            "product_name": product.name,
            "attributes": sku.attributes,
            "price": _decimal(sku.price),
            "status": sku.status,
            "available_quantity": inventory.total_quantity - inventory.reserved_quantity,
        },
    )


async def check_sku_inventory(
    context: ToolContext,
    raw_args: BaseModel,
) -> ToolResult:
    """按 SKU 编码查询可用库存和缺货状态."""
    args = CheckSkuInventoryInput.model_validate(raw_args.model_dump())
    sku, _product = await SkuService(context.session).get_sku_by_code(args.sku_code)
    inventory = await InventoryService(context.session).get_inventory(sku.id)
    available = inventory.total_quantity - inventory.reserved_quantity
    return ToolResult(
        ok=True,
        tool="check_sku_inventory",
        data={
            "sku_code": sku.sku_code,
            "available_quantity": available,
            "stock_status": "IN_STOCK" if available > 0 else "OUT_OF_STOCK",
        },
    )
