from fastapi import APIRouter

from app.api.v1.admin.categories import router as admin_categories_router
from app.api.v1.admin.inventory import router as admin_inventory_router
from app.api.v1.admin.orders import router as admin_orders_router
from app.api.v1.admin.payments import router as admin_payments_router
from app.api.v1.admin.products import router as admin_products_router
from app.api.v1.admin.refunds import router as admin_refunds_router
from app.api.v1.admin.skus import router as admin_skus_router
from app.api.v1.after_sales import (
    admin_router as admin_after_sales_records_router,
)
from app.api.v1.after_sales import order_router as order_after_sales_router
from app.api.v1.after_sales import router as after_sales_router
from app.api.v1.auth import router as auth_router
from app.api.v1.health import router as health_router
from app.api.v1.orders import router as orders_router
from app.api.v1.payments import router as payments_router

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
    orders_router,
    prefix="/orders",
    tags=["Orders"],
)

api_router.include_router(
    order_after_sales_router,
    prefix="/orders",
    tags=["After-sales"],
)

api_router.include_router(
    payments_router,
    prefix="/payments",
    tags=["Payments"],
)

api_router.include_router(
    after_sales_router,
    prefix="/after-sales",
    tags=["After-sales"],
)

api_router.include_router(
    admin_orders_router,
    prefix="/admin/orders",
    tags=["Admin Orders"],
)

api_router.include_router(
    admin_payments_router,
    prefix="/admin/payments",
    tags=["Admin Payments"],
)

api_router.include_router(
    admin_refunds_router,
    prefix="/admin/refunds",
    tags=["Admin Refunds"],
)

api_router.include_router(
    admin_after_sales_records_router,
    prefix="/admin/after-sales",
    tags=["Admin After-sales Records"],
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

api_router.include_router(
    admin_inventory_router,
    prefix="/admin/inventory",
    tags=["Admin Inventory"],
)
