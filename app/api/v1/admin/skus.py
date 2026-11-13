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
    """Update SKU price or status; attributes are immutable."""
    service = SkuService(session)
    sku = await service.update_sku(
        sku_id,
        price=request.price,
        status=request.status,
    )
    return SkuResponse.model_validate(sku)
