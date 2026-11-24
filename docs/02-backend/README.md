# 02 后端

## 职责

FastAPI 提供认证、电商业务、知识库和 Agent API。业务规则和事务在 Service 层, Repository 负责 SQL, API 只做协议和依赖注入。

## 目录

```text
backend/app/
├─ api/            Router/依赖/序列化
├─ core/           配置/安全/异常/日志
├─ db/             MySQL/Redis
├─ infrastructure/ Qdrant/本地存储
├─ models/         ORM
├─ schemas/        Pydantic
├─ repositories/   SQL/行锁
├─ services/       业务/事务
└─ main.py         FastAPI 入口
```

## 启动链路

```text
main.py
→ setup_logging()
→ lifespan: Redis ping
→ register_exception_handlers
→ api_router
→ /api/v1/*
```

## API 分组

### 用户侧

```text
/auth
/orders
/after-sales
/knowledge
/agent
/health
```

### 管理端

```text
/admin/categories
/admin/products
/admin/skus
/admin/inventory
/admin/orders
/admin/after-sales
```

支付和退款 API 已下线。

## 业务模块

| 模块 | Service | 核心职责 |
|---|---|---|
| 认证 | `auth.py` | 注册、登录、Refresh 轮换、退出 |
| 商品 | `product.py`, `sku.py`, `category.py` | SPU/SKU/分类 |
| 库存 | `inventory.py`, `transaction.py` | 入库、调整、预占、释放、扣减、流水 |
| 订单 | `order.py` | 创建 CREATED、取消、发货、送达、完成 |
| 售后 | `after_sale.py` | EXCHANGE 申请、审核、收货、换货补发 |
| 知识库 | `services/rag/` | 解析、切分、Embedding、发布、检索 |

订单库存规则:

```text
创建: 预占
取消: 释放
发货: 预占转扣减
换货收货: 回补
换货补发: 扣减
```

`payments`/`refunds` 表和支付字段作为历史兼容保留, 当前业务不写入。

## 数据库

15 张主要业务表:

```text
users, refresh_sessions
categories, products, skus
inventory, inventory_transactions
orders, order_items, payments, refunds, after_sales
knowledge_documents, knowledge_document_versions, knowledge_chunks
```

Alembic 迁移:

```text
backend/alembic/versions/ 6 个 migration
```

## 事务和一致性

- `get_db` 只创建/关闭 Session, 不自动 commit;
- Service 使用 `transaction_context` 或 `session.begin`;
- 订单、订单项、库存预占在同一事务;
- 取消订单 + 释放库存 + 关闭支付在同一事务;
- 行锁按固定顺序获取, 降低死锁概率;
- 请求级 `idempotency_key` 和唯一约束防重复。

## 测试

```text
backend/tests/api/
backend/tests/core/
backend/tests/integration/
backend/tests/models/
backend/tests/repositories/
backend/tests/schemas/
backend/tests/security/
backend/tests/services/
```
