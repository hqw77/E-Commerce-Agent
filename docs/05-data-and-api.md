# 05 数据模型与 API

## 1. 数据表

当前共 15 张表：

```text
users
refresh_sessions
categories
products
skus
inventory
inventory_transactions
orders
order_items
payments（历史兼容）
refunds（历史兼容）
after_sales
agent_approvals
knowledge_documents
knowledge_document_versions
knowledge_chunks
```

运行时不再写 `payments` / `refunds`。

## 2. 核心关系

```text
User 1 ── N Order
Order 1 ── N OrderItem
Product 1 ── N Sku
Sku 1 ── 1 Inventory
Sku 1 ── N InventoryTransaction
Category 1 ── N Product
Order 1 ── N AfterSale
AfterSale 1 ── 1 Refund（历史）
Payment 1 ── N Refund（历史）
KnowledgeDocument 1 ── N Version 1 ── N Chunk
```

## 3. Product 关键字段

```text
id
product_no        唯一，P001–P010
category_id
name
description
image_url         本地图片相对路径
status            DRAFT/ACTIVE/INACTIVE/ARCHIVED
published_at
archived_at
created_at
updated_at
```

`image_url` 只保存路径，不保存图片二进制。

## 4. Sku / Inventory

SKU：

```text
id
product_id
sku_code
attributes
attributes_hash
price
status
```

库存：

```text
sku_id
total_quantity
reserved_quantity
available_quantity = total - reserved
```

库存流水：

```text
transaction_type
total_delta
reserved_delta
business_type / business_id
operator_id
```

## 5. Order

```text
id
order_no
user_id
status
payment_status
fulfillment_status
total_amount
receiver_*
idempotency_key
request_fingerprint
expires_at
shipped_at
delivered_at
completed_at
cancelled_at
shipping_carrier
tracking_no
```

订单主状态：

```text
CREATED
CANCELLED
COMPLETED
```

历史订单可能包含旧 `PENDING_PAYMENT` / `PAID` 字段值，仅用于读取兼容。

履约状态：

```text
UNSHIPPED
SHIPPED
DELIVERED
COMPLETED
```

## 6. AfterSale

```text
id
after_sales_no
user_id
order_id
order_item_id
type
status
quantity
requested_amount
approved_amount
reason
description
review_note
return_carrier / return_tracking_no
replacement_carrier / replacement_tracking_no
created_at / reviewed_at / completed_at
```

新申请只接受：

```text
EXCHANGE
```

历史 `REFUND_ONLY` / `RETURN_REFUND` 仅用于读取兼容。

## 7. API 分组

### 公开

```text
GET /api/v1/catalog/products
GET /api/v1/catalog/products/{product_no}
GET /api/v1/catalog/categories
```

### 认证

```text
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
GET  /api/v1/auth/me
```

### 普通用户

```text
POST /api/v1/orders
GET  /api/v1/orders
GET  /api/v1/orders/{order_no}
POST /api/v1/orders/{order_no}/cancel

POST /api/v1/orders/{order_no}/after-sales
GET  /api/v1/orders/{order_no}/after-sales

GET  /api/v1/after-sales
GET  /api/v1/after-sales/{after_sales_no}
POST /api/v1/after-sales/{after_sales_no}/cancel
POST /api/v1/after-sales/{after_sales_no}/return-shipment
```

### Agent

```text
POST /api/v1/agent/chat
POST /api/v1/agent/actions/{confirmation_id}/confirm
GET  /api/v1/agent/runs/{trace_id}
```

### 管理员

```text
/api/v1/admin/products
/api/v1/admin/skus
/api/v1/admin/inventory
/api/v1/admin/orders
/api/v1/admin/after-sales
/api/v1/admin/categories
/api/v1/admin/agent/approvals
```

### Agent 审批中心

```text
GET  /api/v1/admin/agent/approvals
GET  /api/v1/admin/agent/approvals/{approval_id}
POST /api/v1/admin/agent/approvals/{approval_id}/approve
POST /api/v1/admin/agent/approvals/{approval_id}/reject
```

审批状态：

```text
pending → approved → executed
        → rejected
        → failed
        → expired
```

审批计划暂存 Redis；`agent_approvals` 表保存持久化审计和执行状态。

### 知识库

```text
/api/v1/knowledge/documents
/api/v1/knowledge/versions
/api/v1/knowledge/publish
/api/v1/knowledge/retry
/api/v1/knowledge/retrieve
```

## 8. 认证约定

```http
Authorization: Bearer <access_token>
```

Access Token 短期有效；Refresh Token 轮换并保存 session hash。

普通用户访问管理 API：

```text
403 Administrator privileges are required
```

## 9. 迁移

Alembic 迁移位于：

```text
backend/alembic/versions/
```

当前包含商品 `image_url` 迁移和知识库表迁移。

常用命令：

```powershell
.venv\Scripts\alembic.exe -c backend\alembic.ini upgrade head
.venv\Scripts\alembic.exe -c backend\alembic.ini check
```

## 10. 数据一致性

关键约束：

- `product_no` 唯一；
- `sku_code` 唯一；
- `user_id + idempotency_key` 唯一；
- `order_id + sku_id` 唯一；
- 库存不允许负数；
- 售后必须关联订单和订单项；
- 订单/售后状态由 Service 校验。
