from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentAdmin
from app.db.session import get_db
from app.schemas.category import (
    CategoryCreateRequest,
    CategoryResponse,
    CategoryTreeNode,
    CategoryUpdateRequest,
)
from app.services.category import CategoryService

router = APIRouter()


@router.post(
    "",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a category",
)
async def create_category(
    request: CategoryCreateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
) -> CategoryResponse:
    """Create a root category or a child category."""
    service = CategoryService(session)
    category = await service.create_category(
        parent_id=request.parent_id,
        name=request.name,
        sort_order=request.sort_order,
    )
    return CategoryResponse.model_validate(category)


@router.get(
    "",
    response_model=list[CategoryResponse],
    summary="List categories",
)
async def list_categories(
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
) -> list[CategoryResponse]:
    """Return all categories as a flat list."""
    service = CategoryService(session)
    categories = await service.list_categories()
    return [CategoryResponse.model_validate(category) for category in categories]


@router.get(
    "/tree",
    response_model=list[CategoryTreeNode],
    summary="Get the category tree",
)
async def get_category_tree(
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
) -> list[CategoryTreeNode]:
    """Return categories nested by parent."""
    service = CategoryService(session)
    return await service.list_tree()


@router.get(
    "/{category_id}",
    response_model=CategoryResponse,
    summary="Get category detail",
)
async def get_category(
    category_id: Annotated[int, Path(ge=1)],
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
) -> CategoryResponse:
    """Return one category by ID."""
    service = CategoryService(session)
    category = await service.get_category(category_id)
    return CategoryResponse.model_validate(category)


@router.patch(
    "/{category_id}",
    response_model=CategoryResponse,
    summary="Update category name, order or status",
)
async def update_category(
    category_id: Annotated[int, Path(ge=1)],
    request: CategoryUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
) -> CategoryResponse:
    """Update category fields; parent_id cannot be changed."""
    service = CategoryService(session)
    category = await service.update_category(
        category_id,
        name=request.name,
        sort_order=request.sort_order,
        status=request.status,
    )
    return CategoryResponse.model_validate(category)
