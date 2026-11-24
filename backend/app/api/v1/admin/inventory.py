"""管理端库存 API.

入库, 调整, 初始化等操作全部通过 InventoryService 写入库存流水.
调用方必须提供 idempotency_key, 以支持安全重试.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentAdmin
from app.db.session import get_db
from app.schemas.inventory import (
    AdjustRequest,
    InventoryInitializeRequest,
    InventoryOperationResponse,
    InventoryResponse,
    InventoryTransactionListResponse,
    InventoryTransactionResponse,
    StockInRequest,
    StockOutRequest,
)
from app.services.inventory import InventoryOperationResult, InventoryService

router = APIRouter()


def _inventory_response(inventory) -> InventoryResponse:
    """计算可用库存并生成响应, 库存账本字段不直接暴露给前端."""
    return InventoryResponse(
        sku_id=inventory.sku_id,
        total_quantity=inventory.total_quantity,
        reserved_quantity=inventory.reserved_quantity,
        available_quantity=(inventory.total_quantity - inventory.reserved_quantity),
    )


def _operation_response(
    result: InventoryOperationResult,
) -> InventoryOperationResponse:
    """把库存操作结果和流水一起返回, 便于前端确认本次变更."""
    return InventoryOperationResponse(
        transaction=InventoryTransactionResponse.model_validate(result.transaction),
        inventory=_inventory_response(result.inventory),
    )


@router.get(
    "/{sku_id}",
    response_model=InventoryResponse,
    summary="Get SKU inventory",
)
async def get_inventory(
    sku_id: Annotated[int, Path(ge=1)],
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
) -> InventoryResponse:
    """查询 SKU 当前库存."""
    service = InventoryService(session)
    inventory = await service.get_inventory(sku_id)
    return _inventory_response(inventory)


@router.post(
    "/{sku_id}/initialize",
    response_model=InventoryOperationResponse,
    summary="Initialize SKU inventory",
)
async def initialize_inventory(
    sku_id: Annotated[int, Path(ge=1)],
    request: InventoryInitializeRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: CurrentAdmin,
) -> InventoryOperationResponse:
    """初始化库存. 只允许从未初始化过的 SKU 执行一次."""
    service = InventoryService(session)
    result = await service.initialize(
        sku_id=sku_id,
        initial_total=request.initial_total,
        idempotency_key=request.idempotency_key,
        operator_id=admin.id,
        remark=request.remark,
    )
    return _operation_response(result)


@router.post(
    "/{sku_id}/stock-in",
    response_model=InventoryOperationResponse,
    summary="Stock in inventory",
)
async def stock_in(
    sku_id: Annotated[int, Path(ge=1)],
    request: StockInRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: CurrentAdmin,
) -> InventoryOperationResponse:
    """入库. 增加总库存并记录一条 STOCK_IN 流水."""
    service = InventoryService(session)
    result = await service.stock_in(
        sku_id=sku_id,
        quantity=request.quantity,
        idempotency_key=request.idempotency_key,
        operator_id=admin.id,
        remark=request.remark,
    )
    return _operation_response(result)


@router.post(
    "/{sku_id}/stock-out",
    response_model=InventoryOperationResponse,
    summary="Direct outbound inventory",
)
async def stock_out(
    sku_id: Annotated[int, Path(ge=1)],
    request: StockOutRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: CurrentAdmin,
) -> InventoryOperationResponse:
    """直接出库. 会校验可用库存, 不允许扣成负数."""
    service = InventoryService(session)
    result = await service.direct_outbound(
        sku_id=sku_id,
        quantity=request.quantity,
        idempotency_key=request.idempotency_key,
        operator_id=admin.id,
        remark=request.remark,
    )
    return _operation_response(result)


@router.post(
    "/{sku_id}/adjust",
    response_model=InventoryOperationResponse,
    summary="Adjust inventory",
)
async def adjust_inventory(
    sku_id: Annotated[int, Path(ge=1)],
    request: AdjustRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: CurrentAdmin,
) -> InventoryOperationResponse:
    """按增量调整库存, 用于盘点或纠错."""
    service = InventoryService(session)
    result = await service.adjust(
        sku_id=sku_id,
        quantity_delta=request.quantity_delta,
        idempotency_key=request.idempotency_key,
        operator_id=admin.id,
        remark=request.remark,
    )
    return _operation_response(result)


@router.get(
    "/{sku_id}/transactions",
    response_model=InventoryTransactionListResponse,
    summary="List SKU inventory transactions",
)
async def list_transactions(
    sku_id: Annotated[int, Path(ge=1)],
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> InventoryTransactionListResponse:
    """分页查询 SKU 库存流水, 用于审计每次数量变化."""
    service = InventoryService(session)
    items, total = await service.list_transactions(
        sku_id,
        page=page,
        page_size=page_size,
    )

    return InventoryTransactionListResponse(
        items=[InventoryTransactionResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )
