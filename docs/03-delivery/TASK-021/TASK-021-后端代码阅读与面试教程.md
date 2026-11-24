# 后端代码阅读与面试教程

> 适用对象：准备用本项目面试后端/全栈/应用开发岗位  
> 范围：**只讲后端，不展开 Agent**  
> 真实定位：本地完成度较高的全栈项目，不是已上线生产系统  
> 面试原则：可以讲架构、取舍和测试，不虚构生产经验

---

# 0. 这份教程怎么用

不要从头到尾背代码。按下面顺序使用：

```text
第 1 遍：看目录和架构图，知道系统有什么
第 2 遍：按 5 条业务链路读代码
第 3 遍：填“接口分析表”
第 4 遍：做面试问答
第 5 遍：用 Swagger + 测试做演示
```

本教程覆盖：

- 后端整体结构；
- 数据库表关系；
- 认证/JWT/Refresh；
- 分类/商品/SKU；
- 库存与库存流水；
- 订单/支付/取消；
- 售后/退款；
- 知识库上传/版本/发布/检索；
- 事务、幂等、并发、权限；
- 测试方法；
- 面试高频问题和参考答案；
- 8 分钟演示脚本；
- 1 天 / 3 天 / 7 天学习计划。

---

# 1. 项目后端全景

## 1.1 技术栈

```text
Python 3.12
FastAPI
Pydantic
异步 SQLAlchemy
MySQL 8
Redis 7
Alembic
JWT
Argon2id
Pytest
Ruff
Mypy
```

## 1.2 后端分层

```text
HTTP 请求
  → FastAPI Router
  → Pydantic Schema
  → Dependency（DB / CurrentUser）
  → Service
  → Repository
  → SQLAlchemy Model
  → MySQL
```

各层职责：

| 层 | 职责 |
|---|---|
| Router | 路由、参数解析、依赖注入、状态码 |
| Schema | 请求/响应校验 |
| Dependency | 当前用户、DB Session、管理员校验 |
| Service | 业务规则、事务、状态机、幂等 |
| Repository | SQL 查询、行锁、条件更新 |
| Model | ORM 映射 |

## 1.3 实际目录

```text
backend/app/
├─ main.py                    # FastAPI 入口、lifespan
├─ api/
│  ├─ router.py               # 总路由
│  ├─ dependencies.py         # CurrentUser / CurrentAdmin
│  └─ v1/
│     ├─ auth.py
│     ├─ orders.py
│     ├─ after_sales.py
│     ├─ payments.py
│     ├─ knowledge.py
│     ├─ health.py
│     └─ admin/
│        ├─ categories.py
│        ├─ products.py
│        ├─ skus.py
│        ├─ inventory.py
│        ├─ orders.py
│        ├─ payments.py
│        └─ refunds.py
├─ core/
│  ├─ config.py
│  ├─ security.py
│  ├─ token.py
│  ├─ exceptions.py
│  ├─ exception_handlers.py
│  └─ logging.py
├─ db/
│  ├─ session.py
│  └─ redis.py
├─ models/
├─ repositories/
├─ schemas/
├─ services/
│  ├─ auth.py
│  ├─ user.py
│  ├─ category.py
│  ├─ product.py
│  ├─ sku.py
│  ├─ inventory.py
│  ├─ transaction.py
│  ├─ order.py
│  ├─ payment.py
│  ├─ refund.py
│  ├─ after_sale.py
│  └─ rag/
└─ middleware/
```

## 1.4 不在这份教程里的内容

暂时跳过：

```text
backend/app/api/v1/agent.py
agent/
```

原因：先把普通后端链路看懂。Agent 需要额外理解 LangGraph、Tool、Prepare/Confirm、RAG 策略。

## 1.5 核心数据库表

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
payments
refunds
after_sales

knowledge_documents
knowledge_document_versions
knowledge_chunks
```

关系：

```text
users
  ├─ refresh_sessions
  ├─ orders
  ├─ after_sales
  └─ knowledge_documents

categories
  └─ products
       └─ skus
            ├─ inventory
            └─ inventory_transactions

orders
  ├─ order_items
  ├─ payments
  ├─ refunds
  └─ after_sales

knowledge_documents
  └─ knowledge_document_versions
       └─ knowledge_chunks
```

---

# 2. 后端请求怎么走

以登录为例：

```text
POST /api/v1/auth/login
  → api/v1/auth.py::login
  → AuthService.login
  → UserRepository.get_by_email
  → verify_password
  → RefreshSessionRepository.create
  → 返回 Access + Refresh Token
```

以订单取消为例：

```text
POST /api/v1/orders/{order_no}/cancel
  → api/v1/orders.py
  → OrderService.cancel_order
  → OrderRepository.get_by_no(for_update=True)
  → 校验 PENDING_PAYMENT
  → InventoryService.release
  → PaymentRepository.save
  → OrderRepository.save
  → commit
```

以知识库上传为例：

```text
POST /api/v1/knowledge/documents
  → CurrentAdmin 校验
  → 读取 UploadFile
  → KnowledgeDocumentService.create_document
  → 文件校验
  → 保存文件
  → 创建 document/version
  → 解析/Chunk/Embedding/Qdrant
  → 版本进入 INDEXED
```

---

# 3. 逐模块精读

## 3.1 应用入口

文件：

```text
backend/app/main.py
```

关键点：

- `setup_logging()`；
- `lifespan` 启动时 ping Redis；
- 关闭时释放 Redis；
- `register_exception_handlers(app)`；
- 挂载 `api_router`，前缀来自配置。

面试回答：

> 应用启动时先确认 Redis 可用，注册统一异常处理，然后挂载所有 v1 路由；关闭时释放 Redis 连接。

---

## 3.2 配置与依赖

相关：

```text
backend/app/core/config.py
backend/app/api/dependencies.py
backend/app/db/session.py
backend/app/db/redis.py
```

### `get_db`

```python
async with AsyncSessionLocal() as session:
    yield session
```

注意：

- 只负责创建/关闭 Session；
- **不自动 commit**；
- 业务 Service 负责事务边界。

这是一个面试可讲的点：

> 我没有让 `get_db` 自动提交，因为有些请求只读，有些请求需要 Service 内部组合多个写操作；事务边界放在 Service 更清晰。

### `CurrentUser`

```text
HTTP Bearer Token
→ TokenService.decode_access_token
→ UserRepository.get_by_id
→ 检查 is_active
→ 返回 User
```

`CurrentAdmin` 在此基础上检查 `is_admin`。

---

## 3.3 认证模块

文件：

```text
backend/app/api/v1/auth.py
backend/app/services/auth.py
backend/app/services/user.py
backend/app/core/security.py
backend/app/core/token.py
```

### 接口

```text
POST /auth/register
POST /auth/login
POST /auth/refresh
GET  /auth/me
POST /auth/logout
```

### 密码

使用 Argon2id：

```python
hash_password()
verify_password()
```

登录时如果用户不存在，会执行 `verify_dummy_password`，消耗同样的哈希时间，避免通过响应时间判断邮箱是否存在。

### Access Token

使用 JWT：

```text
iss
aud
sub = user_id
iat
exp
jti
token_type = access
```

校验时：

- 校验签名；
- 校验 issuer/audience；
- 校验过期；
- 校验 `sub` 是正整数；
- 校验 `token_type=access`；
- 要求 `jti` 存在。

### Refresh Token

不是 JWT，而是：

```text
secrets.token_urlsafe(48)
```

数据库只存 SHA-256 hash：

```text
refresh_sessions.token_hash
```

刷新流程：

```text
旧 refresh token
→ 查 session（行锁）
→ 已撤销：判定 replay，撤销整个 family
→ 已过期：撤销并报错
→ 用户不可用：撤销 family
→ 正常：创建新 refresh，撤销旧 refresh，返回新 token 对
```

重点：

- Refresh 轮换；
- 检测重放；
- family 级撤销；
- 退出登录撤销整个 family；
- 退出接口是幂等的。

面试回答：

> Refresh Token 使用不透明随机串，数据库只保存 SHA-256，刷新时用行锁做轮换；如果已消费的 token 再次出现，会撤销同一 family 的所有会话，降低 token 被重放的风险。

---

## 3.4 分类/商品/SKU

相关：

```text
api/v1/admin/categories.py
api/v1/admin/products.py
api/v1/admin/skus.py

services/category.py
services/product.py
services/sku.py

repositories/category.py
repositories/product.py
repositories/sku.py

models/category.py
models/product.py
models/sku.py
```

核心关系：

```text
Category 1 → N Product 1 → N Sku
```

SKU 是库存、价格、下单的最小单位。

面试要点：

- 为什么价格在 SKU 而不是商品：同一商品不同规格价格不同；
- 为什么库存挂在 SKU：库存按具体规格管理；
- 商品下架时下级 SKU 不可直接售卖；
- 管理端接口必须 `CurrentAdmin`。

---

## 3.5 库存

相关：

```text
api/v1/admin/inventory.py
services/inventory.py
repositories/inventory.py
repositories/inventory_transaction.py
models/inventory.py
models/inventory_transaction.py
```

库存模型：

```text
inventory.total_quantity
inventory.reserved_quantity
available = total - reserved
```

操作：

```text
INITIAL
STOCK_IN
DIRECT_OUTBOUND
ADJUSTMENT
RESERVE
RELEASE
RESERVED_OUTBOUND
```

### 库存变更原则

所有库存变化都写 `inventory_transactions` 流水。

关键点：

1. 先查幂等键；
2. 事务内对 inventory 行加锁；
3. 加锁后再查一次幂等键；
4. 用条件 UPDATE 修改数量；
5. `rowcount != 1` 判定库存不足/初始化冲突；
6. 写流水；
7. 提交。

### 幂等

`inventory_transactions.idempotency_key` 有唯一约束。

重复请求：

- 同参数：返回已有结果；
- 不同参数：`IDEMPOTENCY_KEY_CONFLICT`。

### 并发

`InventoryRepository.update_total()` 使用条件更新：

```text
WHERE total_quantity - reserved_quantity >= required
```

这样不会先读后写造成超卖。

`reserve()`：

```text
WHERE total_quantity - reserved_quantity >= quantity
SET reserved_quantity = reserved_quantity + quantity
```

`deduct_reserved()`：

```text
WHERE reserved_quantity >= quantity
  AND total_quantity >= quantity
SET total_quantity -= quantity,
    reserved_quantity -= quantity
```

### 死锁处理

捕获 MySQL 1213/1205：

- 回滚；
- 查幂等键；
- 有结果返回已有结果；
- 没有则抛并发冲突。

面试回答：

> 库存不是简单 update。我用幂等键 + 行锁 + 条件更新 + 流水表，保证重复请求不会重复扣减，并发时不会超卖；死锁会回滚并尝试按幂等键收敛。

---

## 3.6 订单

相关：

```text
api/v1/orders.py
services/order.py
repositories/order.py
repositories/order_item.py
models/order.py
models/order_item.py
```

### 创建订单

流程：

```text
1. 用 idempotency_key 查已有订单
2. 已有且参数哈希一致 → 直接返回
3. 已有但参数不同 → 409
4. 校验 SKU/商品 ACTIVE
5. 校验可用库存
6. 计算金额
7. 事务内创建 order
8. 创建 order_items
9. 按 sku_id 排序逐个 reserve
10. commit
```

排序很重要：多个订单同时锁多个 SKU 时，统一按 sku_id 排序可以降低死锁概率。

### 幂等键冲突

订单表有：

```text
uq_orders_user_idempotency
```

如果并发插入触发唯一冲突：

- rollback；
- 查已有订单；
- 校验 `request_fingerprint`；
- 相同则返回已有订单；
- 不同则 409。

### 取消订单

```text
1. 对 order 加锁
2. 校验订单属于当前用户
3. 只允许 PENDING_PAYMENT
4. 锁 payment
5. 逐项 release 库存
6. PENDING 支付改为 CLOSED
7. 订单改为 CANCELLED
8. commit
9. 尝试关闭支付宝交易（best effort）
```

### 订单状态

```text
PENDING_PAYMENT
  → PAID
  → SHIPPED
  → DELIVERED
  → COMPLETED

PENDING_PAYMENT
  → CANCELLED

PENDING_PAYMENT
  → CLOSED（超时）
```

面试回答：

> 订单创建把幂等、库存预占和订单明细放在同一个事务；取消订单对订单加锁，只允许待支付状态，然后释放库存并将支付关闭。状态转换全部在 Service 校验，前端和 Agent 不能直接改。

---

## 3.7 支付

相关：

```text
api/v1/payments.py
services/payment.py
services/alipay.py
repositories/payment.py
models/payment.py
```

支持：

```text
MOCK
ALIPAY
```

### 创建支付

- 订单必须属于当前用户；
- 订单必须 PENDING_PAYMENT；
- 不能过期；
- 同一订单已有支付时，不能随意换渠道；
- 已有 PENDING/SUCCESS 支付可复用；
- FAILED/CLOSED 不能重新创建。

### 支付成功

`_apply_success()` 处理：

- 重复成功；
- 订单已取消/关闭后的迟到支付；
- 订单超时后的迟到支付；
- 正常支付。

正常支付：

```text
inventory.deduct_reserved
order.status = PAID
order.payment_status = PAID
```

迟到支付：

```text
payment.exception_reason = LATE_PAYMENT
更新支付金额/支付时间
订单可能保持 CANCELLED/CLOSED
```

面试回答：

> 支付成功不是简单把订单改成 PAID。要处理重复回调、订单取消后的迟到支付和超时后的迟到支付；正常支付才把预占库存转成实际出库。

---

## 3.8 售后

相关：

```text
api/v1/after_sales.py
services/after_sale.py
repositories/after_sale.py
models/after_sale.py
```

申请流程：

```text
1. 锁订单
2. 校验订单归属
3. 锁订单项
4. 幂等键检查
5. 同一订单项不能有重复活跃售后
6. 订单支付状态必须 PAID / PARTIALLY_REFUNDED
7. REFUND_ONLY 要求未发货
8. 退货/换货要求已送达
9. 校验售后时间窗口
10. 创建 PENDING_REVIEW
```

状态：

```text
PENDING_REVIEW
  → REFUNDING
  → REFUNDED

PENDING_REVIEW
  → WAITING_RETURN
  → RETURN_SHIPPED
  → COMPLETED

PENDING_REVIEW
  → REJECTED

PENDING_REVIEW
  → CANCELLED
```

审核加锁顺序：

```text
order → item → payment → after-sale
```

这是为了避免死锁，面试可以主动提。

面试回答：

> 售后申请会锁订单和订单项，校验归属、支付状态、履约状态和时间窗口；同一订单项只允许一个活跃售后。审核时按固定顺序加锁，再决定退款、退货或换货。

---

## 3.9 退款

相关：

```text
services/refund.py
repositories/refund.py
models/refund.py
```

关键点：

- 退款金额不能超过支付金额；
- 已占用退款金额要算进去；
- 退款幂等键；
- 退款记录和售后关联；
- 支付宝退款要处理未知结果；
- 未知结果不能盲目重发，需要查询；
- 退款成功才更新支付/订单/售后状态。

面试回答：

> 退款先计算已占用金额，防止超额退款；退款记录有幂等键；支付宝退款请求结果未知时保持 PROCESSING，后续查询而不是重复退款。

---

## 3.10 知识库后端

相关：

```text
api/v1/knowledge.py
services/rag/document_service.py
services/rag/parser.py
services/rag/chunker.py
services/rag/embedding.py
services/rag/retrieval_service.py
repositories/knowledge.py
models/knowledge_*.py
```

### 上传

- 只有管理员能上传；
- 校验文件类型；
- 校验大小；
- 计算 hash；
- 保存文件；
- 创建 document；
- 创建 version；
- 解析、Chunk、Embedding、写 Qdrant；
- version 进入 INDEXED。

### 版本

```text
UPLOADED
PROCESSING
INDEXED
PUBLISHED
SUPERSEDED
FAILED
```

发布：

- 只允许 INDEXED；
- 当前 published version 更新；
- 旧版本 SUPERSEDED；
- 检索只使用当前发布版本。

### 检索

```text
CurrentUser
→ list_retrievable_versions
  - ACTIVE
  - current_published_version_id
  - PUBLISHED
  - 非管理员只允许 PUBLIC
→ Qdrant 检索
→ MySQL 权威校验
→ 丢弃 stale point
→ 返回 RetrievalItem
```

要点：

- MySQL 是权威数据源；
- Qdrant 只是向量索引；
- 权限在检索前过滤；
- 删除/旧版本不会因为 Qdrant stale 而泄露。

面试回答：

> 知识库不是“上传后直接进 Qdrant 就完事”。文档、版本、Chunk 的权威数据在 MySQL，Qdrant 只存向量和版本 ID。检索先查 MySQL 允许的发布版本，再查 Qdrant，最后回 MySQL 校验，避免越权和 stale index。

---

# 4. 事务、幂等、并发

这是后端面试最值钱的部分。

## 4.1 事务边界

项目使用：

```python
async with transaction_context(session):
    ...
```

行为：

- 如果当前 Session 已有事务，复用并提交/回滚；
- 如果没有，开启新事务。

原则：

- 一个业务操作放在一个事务；
- 订单 + 明细 + 库存预占在一个事务；
- 取消订单 + 释放库存 + 关闭支付在一个事务；
- 售后审核 + 退款记录在一个事务；
- 外部支付宝调用放在事务外，避免长事务。

## 4.2 幂等

项目有三类幂等：

```text
订单：user_id + idempotency_key + request_fingerprint
库存：inventory_transactions.idempotency_key
退款/售后：各自的 idempotency_key
```

回答模板：

> 幂等不是“重复请求返回 200”，而是同一业务键只产生一次副作用；同键不同参数要明确冲突，不能悄悄复用。

## 4.3 并发

手段：

- `SELECT ... FOR UPDATE`；
- 条件 UPDATE + rowcount；
- 唯一约束；
- 固定加锁顺序；
- 捕获死锁后回滚；
- Redis 锁/原子操作（Agent 和支付场景）。

## 4.4 为什么不用一个大事务包所有东西

- 外部 HTTP 调用可能很慢；
- 事务持有行锁会阻塞；
- 支付回调/退款查询需要分阶段；
- 事务应该短，状态需要可恢复。

---

# 5. 七天学习计划

## Day 1：基础设施 + 认证

读：

```text
main.py
api/router.py
api/dependencies.py
core/config.py
db/session.py
db/redis.py
auth.py / services/auth.py / core/token.py
```

产出：

- 登录/刷新/退出时序图；
- 能解释 `get_db` 为什么不自动 commit；
- 能解释 Refresh 重放检测。

## Day 2：分类/商品/SKU

读：

```text
api/v1/admin/categories.py
api/v1/admin/products.py
api/v1/admin/skus.py
services/category.py/product.py/sku.py
repositories + models
```

产出：

- 表关系图；
- 能解释为什么库存挂在 SKU；
- 能解释管理员权限。

## Day 3：库存

读：

```text
services/inventory.py
repositories/inventory.py
services/transaction.py
```

产出：

- 入库/调整/预占/释放/出库流程图；
- 幂等键和行锁说明；
- 死锁处理说明。

## Day 4：订单 + 支付

读：

```text
services/order.py
services/payment.py
api/v1/orders.py
api/v1/payments.py
```

产出：

- 下单时序图；
- 取消订单时序图；
- 订单状态机；
- 支付迟到处理。

## Day 5：售后 + 退款

读：

```text
services/after_sale.py
services/refund.py
api/v1/after_sales.py
```

产出：

- 售后状态机；
- 审核加锁顺序；
- 退款金额校验。

## Day 6：知识库后端

读：

```text
api/v1/knowledge.py
services/rag/document_service.py
parser.py
chunker.py
retrieval_service.py
```

产出：

- 上传/发布/检索链路；
- MySQL 和 Qdrant 的关系；
- ACL 过滤位置。

## Day 7：测试 + 面试模拟

- 跑全量测试；
- 背 2 分钟项目介绍；
- 做 15 道问答；
- 用 Swagger 演示一遍；
- 录屏备份。

---

# 6. 面试高频问题和参考答案

下面不是让逐字背，而是理解“回答结构”。

## Q1：介绍一下后端架构

> 后端是 FastAPI + 异步 SQLAlchemy，按 Router → Schema → Service → Repository → Model 分层。Router 只处理协议和依赖注入，Service 负责业务规则、事务和状态机，Repository 负责 SQL，Model 做 ORM 映射。这样权限、事务和状态转换都集中在 Service，不会散落在接口里。

## Q2：为什么 `get_db` 不自动 commit？

> 因为一个请求里可能有多个业务操作，事务边界应该由 Service 决定。比如订单创建要同时写订单、订单项和库存流水，不能每个 Repository 自己提交。只读请求也不需要 commit。Service 用 `transaction_context` 统一提交或回滚。

## Q3：JWT Access Token 怎么校验？

> 校验签名、issuer、audience、过期时间、token_type 和 jti；`sub` 必须是合法正整数。用户身份最终从数据库 CurrentUser 再查一次，避免只信 token 里的信息。

## Q4：Refresh Token 为什么不用 JWT？

> Refresh 需要可撤销、可轮换和重放检测，所以用不透明随机串，数据库只存 SHA-256。刷新时行锁轮换，已消费 token 再次出现就撤销整个 token family。

## Q5：库存怎么防超卖？

> 先对 inventory 行加锁，然后用条件 UPDATE：`total - reserved >= quantity` 才增加 reserved，`rowcount` 不是 1 就判定库存不足。库存变化同时写流水，幂等键防重复。

## Q6：库存幂等怎么做？

> `inventory_transactions.idempotency_key` 唯一。先查已有流水；事务内加锁后再查一次，防止并发；同键同参数返回已有结果，同键不同参数抛冲突。

## Q7：订单创建怎么保证一致性？

> 订单、订单项、库存预占在同一个事务；先做幂等检查，再校验 SKU/库存，创建订单和明细，按 sku_id 排序预占库存，最后提交。唯一键冲突时回滚并根据幂等键返回已有订单或报参数冲突。

## Q8：为什么多 SKU 要按 sku_id 排序？

> 固定加锁顺序，降低两个订单同时锁多个 SKU 时的死锁概率。这是并发控制的常见做法。

## Q9：取消订单流程？

> 对订单行加锁，校验归属和 PENDING_PAYMENT，锁支付记录，逐项释放库存，关闭 PENDING 支付，订单改 CANCELLED，同一事务提交。支付宝关单放在事务外，best effort。

## Q10：支付回调怎么防重复？

> 支付记录状态和订单状态都做校验；已经是 SUCCESS 的直接返回。支付金额、渠道、订单归属都校验。迟到支付单独标记 `LATE_PAYMENT`，不能把已取消订单重新改成已支付。

## Q11：订单状态机怎么设计？

> 状态转换集中在 Service，不暴露给前端。只允许 PENDING_PAYMENT → PAID → SHIPPED → DELIVERED → COMPLETED，以及 PENDING_PAYMENT → CANCELLED/CLOSED。非法转换抛冲突异常。

## Q12：售后申请限制？

> 订单必须属于当前用户，支付状态必须是 PAID/部分退款；仅退款要求未发货，退货/换货要求已送达；同一订单项不能有活跃售后；还要校验售后时间窗口。

## Q13：售后审核怎么防并发？

> 先查关系但不加锁，然后按 order → item → payment → after-sale 固定顺序加锁；状态必须是 PENDING_REVIEW；支付必须可退；审核和退款记录在一个事务内。

## Q14：退款金额怎么控制？

> 计算该支付下已占用退款金额，新退款不能超过支付金额；退款记录有幂等键；支付/订单/售后状态一起更新。

## Q15：知识库为什么 MySQL + Qdrant？

> MySQL 保存文档、版本、Chunk 和权限，是权威数据；Qdrant 只做向量召回。检索先查 MySQL 允许的发布版本，再查 Qdrant，最后回 MySQL 校验，避免越权和 stale point。

## Q16：文档发布流程？

> 上传后创建版本，解析/Chunk/Embedding/Qdrant；只有 INDEXED 才能发布；发布时更新当前 published version，旧版本 SUPERSEDED；检索只使用当前发布版本。

## Q17：PUBLIC / ADMIN_ONLY 怎么控制？

> 检索前用 `list_retrievable_versions` 按当前用户过滤：普通用户只允许 ACTIVE + PUBLIC + 当前发布版本；管理员可以看 ADMIN_ONLY。Qdrant 只收到允许的 version_id，MySQL 再校验。

## Q18：文件上传怎么防问题？

> 限制大小和类型，校验文件名/MIME，计算 hash，文件存储与数据库记录分开，解析失败标记 FAILED，只有管理员能上传。

## Q19：为什么外部支付调用不放在事务里？

> 外部 HTTP 可能慢或超时，长事务会持有行锁。项目先把退款/支付状态改成 PROCESSING 并提交，再调用外部；未知结果通过查询收敛，避免重复退款。

## Q20：异常怎么统一处理？

> Service 抛业务异常，统一异常处理器映射 HTTP 状态码和错误码；API 不写散落的 try/except；敏感内部错误不直接暴露给客户端。

## Q21：测试怎么做？

> Service 单元测试覆盖规则，集成测试覆盖 API + MySQL/Redis，并发/幂等测试覆盖库存和确认，异常测试覆盖越权/重复/非法状态，E2E 覆盖浏览器主流程。

## Q22：为什么不用微服务？

> 当前业务规模不需要。模块化单体更容易保证事务一致性、部署简单、调试成本低。订单、库存、售后本身就强关联，拆服务会引入分布式事务和最终一致性复杂度。

## Q23：如果流量变大先改什么？

> 先做观测和瓶颈定位，不盲目微服务。可能先加索引、连接池、缓存、读副本、异步任务、限流；库存/订单写路径仍以数据库事务和幂等为核心。

## Q24：这个项目有什么不足？

> 没有生产部署、真实支付未完成、HITL 未做、RAG 评测样本小、Trace 是进程内 Buffer、状态文档滞后、代码未提交。这些是工程收口问题，不是假装没有。

## Q25：你从项目里学到什么？

> 最重要的是：LLM/Agent 不能成为业务权限边界；关键写操作要显式 Prepare/Confirm；事务、幂等、并发和 ACL 必须由后端保证；可观测性和测试比“接一个大模型”更重要。

---

# 7. 三个必须准备的 STAR 故事

## 故事 1：库存并发与幂等

```text
S：重复请求/并发可能造成超卖或重复流水
T：保证库存数量和流水一致
A：行锁 + 条件 UPDATE + 唯一幂等键 + 流水表 + 死锁回滚
R：重复请求可收敛，并发不足库存被拒绝，流水可审计
```

## 故事 2：订单状态机

```text
S：支付、取消、售后都可能改订单
T：防止非法状态转换
A：状态校验集中在 OrderService，行锁，迟到支付单独处理
R：非法操作返回冲突，订单状态可预测
```

## 故事 3：知识库版本/权限

```text
S：文档有多版本，Qdrant 可能 stale，还有 ACL
T：只返回允许的当前发布版本
A：MySQL 权威 + PUBLISHED 版本 + ACL 预过滤 + 检索后校验
R：旧版本/越权文档不会返回，Source 可追溯
```

---

# 8. 8 分钟面试演示

## 0:00–1:00 项目定位

> 本地全栈电商项目，重点后端一致性、权限和可验证性；不冒充生产系统。

## 1:00–2:00 架构

画：

```text
React → FastAPI → Service → Repository → MySQL
                         ↘ Redis
```

## 2:00–4:00 认证 + 商品/库存

- 登录；
- 分类/商品/SKU；
- 库存入库；
- 展示流水。

## 4:00–6:00 订单/售后

- 创建订单；
- 查看订单状态；
- 取消订单；
- 售后申请/审核。

## 6:00–7:00 知识库

- 文档版本；
- 发布；
- 检索；
- 讲 MySQL/Qdrant 权威关系。

## 7:00–8:00 测试和边界

- 372 后端/Agent 测试；
- Ruff/Mypy；
- 未上线、真实支付未做、测试数据保留。

---

# 9. 代码阅读检查表

每读完一个模块，勾选：

- [ ] 能说出 Router 文件；
- [ ] 能说出 Service 方法；
- [ ] 能说出 Repository 查询；
- [ ] 能说出涉及的表；
- [ ] 能说出事务边界；
- [ ] 能说出权限校验；
- [ ] 能说出幂等/并发；
- [ ] 能说出异常码；
- [ ] 能找到对应测试。

如果这 9 项都能答，模块就算读懂了。

---

# 10. 最后提醒

面试时不要：

- 背代码；
- 说“生产级”；
- 说“全部完成”；
- 把 Agent 的 100% RAG 指标当生产结论；
- 忽略事务、幂等和权限。

最值得展示的是：

```text
1. 能把一条请求从 Router 讲到 DB
2. 能解释事务边界
3. 能解释幂等和并发
4. 能解释 ACL 和权威数据源
5. 能承认边界和不足
```

一句话：

> **先把五条业务链路读通，再用三个技术难点证明你不是只会 CRUD。**

---

# 11. 两分钟项目介绍模板

> 这是一个本地完成度较高的全栈电商项目，后端用 FastAPI + 异步 SQLAlchemy，数据库 MySQL，Redis 做限流、会话和临时状态，前端 React。业务侧包含认证、分类/商品/SKU、库存、订单、支付、售后和知识库。
>
> 我重点做的是后端一致性和安全边界：订单创建把订单明细和库存预占放在同一事务里，用幂等键和唯一约束防重复；库存用行锁、条件更新和流水表防超卖；售后和退款按固定顺序加锁，控制金额和状态转换。
>
> 知识库侧，MySQL 保存文档、版本、Chunk 和权限，Qdrant 只做向量索引。检索先按当前用户的 PUBLIC/ADMIN_ONLY 权限取允许的发布版本，再查 Qdrant，最后回 MySQL 校验，避免越权和 stale point。
>
> 项目有 372 个后端/Agent 测试和 10 个 Playwright E2E。它没有生产上线，真实支付和 HITL 还没完成，我会明确说明这些边界。

---

# 12. API 速查

## 认证

```text
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/refresh
GET  /api/v1/auth/me
POST /api/v1/auth/logout
```

## 管理端

```text
/api/v1/admin/categories
/api/v1/admin/products
/api/v1/admin/skus
/api/v1/admin/inventory
/api/v1/admin/orders
/api/v1/admin/payments
/api/v1/admin/refunds
/api/v1/admin/after-sales
```

## 用户业务

```text
/api/v1/orders
/api/v1/after-sales
/api/v1/payments
```

## 知识库

```text
POST   /api/v1/knowledge/documents
GET    /api/v1/knowledge/documents
GET    /api/v1/knowledge/documents/{id}
POST   /api/v1/knowledge/documents/{id}/versions
GET    /api/v1/knowledge/documents/{id}/versions/{version_id}
POST   /api/v1/knowledge/documents/{id}/versions/{version_id}/publish
POST   /api/v1/knowledge/documents/{id}/versions/{version_id}/retry
DELETE /api/v1/knowledge/documents/{id}
POST   /api/v1/knowledge/retrieve
```

## 健康检查

```text
GET /api/v1/health/live
GET /api/v1/health/ready
```

---

# 13. 面试前 24 小时检查表

- [ ] 能画出后端分层图；
- [ ] 能画出 15 张表的关系图；
- [ ] 能画出登录/刷新/退出；
- [ ] 能画出下单/取消；
- [ ] 能画出库存入库/预占/释放；
- [ ] 能画出售后状态；
- [ ] 能解释至少一个事务边界；
- [ ] 能解释至少一个幂等场景；
- [ ] 能解释一个并发/死锁处理；
- [ ] 能解释 PUBLIC/ADMIN_ONLY；
- [ ] 能解释 MySQL/Qdrant 权威关系；
- [ ] 能跑通测试；
- [ ] 能打开 Swagger 演示；
- [ ] 能诚实说明未上线、真实支付未完成；
- [ ] 准备录屏，防止现场网络/模型失败。
