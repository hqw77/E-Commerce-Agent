"""管理端 SKU API.

SKU 属性在创建后保持不变, 允许调整价格和上下架状态.
价格变化不会回写历史订单, 订单项保存下单时的快照.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentAdmin
from app.db.session import get_db
from app.schemas.sku import SkuResponse, SkuUpdateRequest
from app.services.sku import SkuService

router = APIRouter()


@router.patch(
    "/{sku_id}",
    response_model=SkuResponse,
    summary="Update SKU price or status",
)
async def update_sku(
    sku_id: Annotated[int, Path(ge=1)],
    request: SkuUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
) -> SkuResponse:
    """更新 SKU 价格或状态. 属性不可变, 避免历史订单语义漂移."""
    service = SkuService(session)
    sku = await service.update_sku(
        sku_id,
        price=request.price,
        status=request.status,
    )
    return SkuResponse.model_validate(sku)
