from fastapi import APIRouter

from app.api.v1.admin.categories import router as admin_categories_router
from app.api.v1.admin.products import router as admin_products_router
from app.api.v1.admin.skus import router as admin_skus_router
from app.api.v1.auth import router as auth_router
from app.api.v1.health import router as health_router

api_router = APIRouter()

api_router.include_router(
    health_router,
    prefix="/health",
    tags=["Health"],
)

api_router.include_router(
    auth_router,
    prefix="/auth",
    tags=["Authentication"],
)

api_router.include_router(
    admin_categories_router,
    prefix="/admin/categories",
    tags=["Admin Categories"],
)

api_router.include_router(
    admin_products_router,
    prefix="/admin/products",
    tags=["Admin Products"],
)

api_router.include_router(
    admin_skus_router,
    prefix="/admin/skus",
    tags=["Admin SKUs"],
)
