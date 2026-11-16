# TASK-014 API 契约矩阵

> 实施更新：分类管理 UI、知识库发布/重试/上传版本已补齐；以下状态为 TASK-014 完成后的最终状态。

> 生成依据：`backend/app/main.py` 的 OpenAPI schema。
> 本文件只记录现状和计划，不代表未覆盖接口已被实现。

## 1. 统计

- OpenAPI 路径数量：65
- Method + Path 条目数量：75
- 状态定义：`covered` 已有前端模块/页面；`backend-only` 后端已有但前端页面未使用；`gap` 本任务需要补的前端联调缺口；`n/a` 运维或外部回调。

## 2. 契约明细

| Method | Path | 前端模块 | 状态 |
|---|---|---|---|
| GET | `/api/v1/admin/after-sales` | src/api/afterSales.ts | covered |
| GET | `/api/v1/admin/after-sales/{after_sales_no}` | src/api/afterSales.ts | covered |
| POST | `/api/v1/admin/after-sales/{after_sales_no}/approve` | src/api/afterSales.ts | backend-only |
| POST | `/api/v1/admin/after-sales/{after_sales_no}/complete-exchange` | src/api/afterSales.ts | backend-only |
| POST | `/api/v1/admin/after-sales/{after_sales_no}/receive` | src/api/afterSales.ts | backend-only |
| POST | `/api/v1/admin/after-sales/{after_sales_no}/reject` | src/api/afterSales.ts | backend-only |
| GET | `/api/v1/admin/categories` | src/api/products.ts | covered |
| POST | `/api/v1/admin/categories` | src/api/products.ts | covered（分类管理 UI） |
| GET | `/api/v1/admin/categories/tree` | src/api/products.ts | covered |
| GET | `/api/v1/admin/categories/{category_id}` | src/api/products.ts | covered |
| PATCH | `/api/v1/admin/categories/{category_id}` | src/api/products.ts | covered（分类管理 UI） |
| GET | `/api/v1/admin/inventory/{sku_id}` | src/api/inventory.ts | covered |
| POST | `/api/v1/admin/inventory/{sku_id}/adjust` | src/api/inventory.ts | covered |
| POST | `/api/v1/admin/inventory/{sku_id}/initialize` | src/api/inventory.ts | backend-only |
| POST | `/api/v1/admin/inventory/{sku_id}/stock-in` | src/api/inventory.ts | covered |
| POST | `/api/v1/admin/inventory/{sku_id}/stock-out` | src/api/inventory.ts | backend-only |
| GET | `/api/v1/admin/inventory/{sku_id}/transactions` | src/api/inventory.ts | covered |
| GET | `/api/v1/admin/orders` | src/api/orders.ts | covered |
| POST | `/api/v1/admin/orders/close-expired` | src/api/orders.ts | backend-only |
| GET | `/api/v1/admin/orders/{order_no}` | src/api/orders.ts | covered |
| POST | `/api/v1/admin/orders/{order_no}/complete` | src/api/orders.ts | backend-only |
| POST | `/api/v1/admin/orders/{order_no}/deliver` | src/api/orders.ts | backend-only |
| POST | `/api/v1/admin/orders/{order_no}/ship` | src/api/orders.ts | backend-only |
| GET | `/api/v1/admin/payments` | src/api/orders.ts | backend-only：listPayments 已有函数但页面未使用 |
| GET | `/api/v1/admin/payments/{payment_no}` | src/api/orders.ts | backend-only：listPayments 已有函数但页面未使用 |
| POST | `/api/v1/admin/payments/{payment_no}/sync` | src/api/orders.ts | backend-only：listPayments 已有函数但页面未使用 |
| GET | `/api/v1/admin/products` | src/api/products.ts | covered |
| POST | `/api/v1/admin/products` | src/api/products.ts | covered |
| GET | `/api/v1/admin/products/{product_id}` | src/api/products.ts | covered |
| PATCH | `/api/v1/admin/products/{product_id}` | src/api/products.ts | covered |
| POST | `/api/v1/admin/products/{product_id}/activate` | src/api/products.ts | covered |
| POST | `/api/v1/admin/products/{product_id}/archive` | src/api/products.ts | covered |
| POST | `/api/v1/admin/products/{product_id}/deactivate` | src/api/products.ts | covered |
| GET | `/api/v1/admin/products/{product_id}/skus` | src/api/products.ts | covered |
| POST | `/api/v1/admin/products/{product_id}/skus` | src/api/products.ts | covered |
| GET | `/api/v1/admin/refunds` | 未映射 | backend-only |
| POST | `/api/v1/admin/refunds` | 未映射 | backend-only |
| GET | `/api/v1/admin/refunds/{refund_no}` | 未映射 | backend-only |
| POST | `/api/v1/admin/refunds/{refund_no}/retry` | 未映射 | backend-only |
| POST | `/api/v1/admin/refunds/{refund_no}/sync` | 未映射 | backend-only |
| PATCH | `/api/v1/admin/skus/{sku_id}` | src/api/products.ts | covered |
| GET | `/api/v1/after-sales/{after_sales_no}` | backend API only（管理端页面使用 admin 路径） | backend-only |
| POST | `/api/v1/after-sales/{after_sales_no}/cancel` | backend API only（管理端页面使用 admin 路径） | backend-only |
| POST | `/api/v1/after-sales/{after_sales_no}/return-shipment` | backend API only（管理端页面使用 admin 路径） | backend-only |
| POST | `/api/v1/agent/actions/{confirmation_id}/confirm` | src/api/agent.ts | covered |
| POST | `/api/v1/agent/chat` | src/api/agent.ts | covered |
| POST | `/api/v1/auth/login` | src/api/auth.ts | covered |
| POST | `/api/v1/auth/logout` | src/api/auth.ts | covered |
| GET | `/api/v1/auth/me` | src/api/auth.ts | covered |
| POST | `/api/v1/auth/refresh` | src/api/auth.ts | covered |
| POST | `/api/v1/auth/register` | src/api/auth.ts | covered |
| GET | `/api/v1/health/live` | 运维接口 | n/a |
| GET | `/api/v1/health/ready` | 运维接口 | n/a |
| GET | `/api/v1/knowledge/documents` | src/api/knowledge.ts | covered |
| POST | `/api/v1/knowledge/documents` | src/api/knowledge.ts | covered |
| DELETE | `/api/v1/knowledge/documents/{document_id}` | src/api/knowledge.ts | covered |
| GET | `/api/v1/knowledge/documents/{document_id}` | src/api/knowledge.ts | covered |
| POST | `/api/v1/knowledge/documents/{document_id}/versions` | src/api/knowledge.ts | covered（上传新版本 UI） |
| GET | `/api/v1/knowledge/documents/{document_id}/versions/{version_id}` | src/api/knowledge.ts | backend-only |
| POST | `/api/v1/knowledge/documents/{document_id}/versions/{version_id}/publish` | src/api/knowledge.ts | covered（发布/重试/上传版本 UI） |
| POST | `/api/v1/knowledge/documents/{document_id}/versions/{version_id}/retry` | src/api/knowledge.ts | covered（发布/重试/上传版本 UI） |
| POST | `/api/v1/knowledge/retrieve` | src/api/knowledge.ts | covered |
| GET | `/api/v1/orders` | backend API only（管理端页面使用 admin 路径） | backend-only |
| POST | `/api/v1/orders` | backend API only（管理端页面使用 admin 路径） | backend-only |
| GET | `/api/v1/orders/{order_no}` | backend API only（管理端页面使用 admin 路径） | backend-only |
| GET | `/api/v1/orders/{order_no}/after-sales` | backend API only（管理端页面使用 admin 路径） | backend-only |
| POST | `/api/v1/orders/{order_no}/after-sales` | backend API only（管理端页面使用 admin 路径） | backend-only |
| POST | `/api/v1/orders/{order_no}/cancel` | backend API only（管理端页面使用 admin 路径） | backend-only |
| POST | `/api/v1/orders/{order_no}/payments` | backend API only（管理端页面使用 admin 路径） | backend-only |
| GET | `/api/v1/payments` | backend API only（管理端页面使用 admin 路径） | backend-only |
| POST | `/api/v1/payments/alipay/notify` | backend API only（管理端页面使用 admin 路径） | backend-only |
| GET | `/api/v1/payments/alipay/return` | backend API only（管理端页面使用 admin 路径） | backend-only |
| GET | `/api/v1/payments/{payment_no}` | backend API only（管理端页面使用 admin 路径） | backend-only |
| POST | `/api/v1/payments/{payment_no}/mock-fail` | backend API only（管理端页面使用 admin 路径） | backend-only |
| POST | `/api/v1/payments/{payment_no}/mock-success` | backend API only（管理端页面使用 admin 路径） | backend-only |

## 3. 本任务确定的缺口

1. 分类管理：新增最小分类列表、创建、编辑页面，复用 `/admin/categories`。
2. 知识库：新增发布 INDEXED 版本、重试 FAILED 版本、上传新版本操作。
3. 浏览器 E2E：新增 Playwright 工程、配置和核心流程用例。
4. Payment：只验证订单支付状态和独立 Payment API，不建立未提供的 Order-Payment 关联。
5. 订单/售后编号搜索：后端没有 keyword 参数，继续记录为当前页过滤限制，不扩展 API。

## 4. 不在本任务修改

- 不修改 PaymentResponse 或任何数据库结构；
- 不新增订单、库存、支付、售后业务规则；
- 不实现支付沙箱、退款或回调真实链路；
- 不实现未提供的管理端审核、退款、发货按钮；
- 不改变 `/api/v1` 路径和请求/响应结构。
