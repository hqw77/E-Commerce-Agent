# 05 数据模型与 API

## 1. 数据表

当前共 13 张业务表：

```text
users
categories
products
skus
inventory
inventory_transactions
orders
order_items
after_sales
agent_approvals
knowledge_documents
knowledge_document_versions
knowledge_chunks
```

支付/退款表已删除。

## 2. 核心关系

```text
User 1 ── N Order
Order 1 ── N OrderItem
Product 1 ── N Sku
Sku 1 ── 1 Inventory
Sku 1 ── N InventoryTransaction
Category 1 ── N Product
Order 1 ── N AfterSale
KnowledgeDocument 1 ── N Version 1 ── N Chunk
User 1 ── N AgentApproval
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
fulfillment_status
total_amount
receiver_*
idempotency_key
request_fingerprint
shipped_at
delivered_at
completed_at
cancelled_at
shipping_carrier
tracking_no
```

订单表不再包含支付状态、支付金额、退款金额、支付时间和支付超时字段。

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
POST /api/v1/knowledge/documents
GET  /api/v1/knowledge/documents
GET  /api/v1/knowledge/documents/{document_id}
POST /api/v1/knowledge/documents/{document_id}/versions
POST /api/v1/knowledge/documents/{document_id}/versions/{version_id}/publish
POST /api/v1/knowledge/documents/{document_id}/versions/{version_id}/retry
DELETE /api/v1/knowledge/documents/{document_id}
POST /api/v1/knowledge/retrieve
```

## 8. 认证约定

```http
Authorization: Bearer <access_token>
```

Access Token 默认有效期 24 小时；过期后重新登录，不再使用 Refresh Token。

普通用户访问管理 API：

```text
403 Administrator privileges are required
```

## 9. 迁移

Alembic 迁移位于：

```text
backend/alembic/versions/
```

当前 head：

```text
33d629302f1f  删除 refresh_sessions, 完成 Access Token-only 认证
5d7a27f8ba5c  删除订单支付遗留字段
80b9bbf33d5a  删除 payments / refunds 表
```

当前数据库共 13 张业务表，不再有 `payments`、`refunds`、`refresh_sessions`。

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
