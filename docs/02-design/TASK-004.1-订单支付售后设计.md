# TASK-004.1 订单、支付与售后设计方案（第一版收敛稿）

> 文档状态：设计 Review 中，尚未冻结  
> 适用范围：TASK-004.2～004.9  
> 本文件是 TASK-004 第一版落地的设计基线候选稿。

## 0. 收敛说明

本版按照“第一版可靠、完整、可运行、可解释”的原则收敛：

- 保留订单、库存、支付、退款、售后的基本业务闭环；
- 保留必要的事务、行锁、条件更新、幂等和权限保护；
- 删除多笔成功支付对账、STOCK_ERROR 自动恢复、退款未知状态自动收敛等复杂体系；
- 对无法自动处理的异常，明确记录日志、告警或交管理员处理；
- 不把理论上的极端竞争窗口全部纳入第一版实现。

### 0.1 与上一版的主要差异

| 上一版 | 第一版收敛稿 |
|---|---|
| 同一订单允许多笔支付尝试，区分主支付/重复支付 | 一个订单只创建一个支付单，`payments.order_id` 唯一 |
| `is_primary`、`DUPLICATE_PAYMENT`、多支付对账 | 删除 |
| STOCK_ERROR 独立事务、重新判定主支付、修复库存接口 | 删除；回调失败整体回滚、记录 critical 日志、人工处理 |
| 退款未知状态自动收敛、复杂处理中金额恢复 | 保留基本额度占用；不做自动收敛，人工查询/重试 |
| 复杂支付/退款对账状态组合 | 只保留基本支付、退款状态和 `exception_reason` |
| 大量理论并发竞争专项测试 | 保留核心并发测试：下单、取消、支付回调、退款额度、售后申请 |
| 换货 `REPLACEMENT_PENDING` 等细分状态 | 收敛为现有基本状态 |

### 0.2 简化不等于删除正确性

以下能力必须保留：

- 数据库事务；
- 库存行锁和条件 UPDATE；
- 防止超卖；
- 支付回调幂等；
- 防止重复回调重复扣库存；
- 退款金额不超过支付金额；
- 权限校验和用户数据隔离；
- 金额使用 `Decimal`。

以下两项看起来增加了状态/锁，但属于第一版基本正确性所需，不能删除：

1. **退款 `PENDING`/`PROCESSING` 额度占用**  
   如果并发创建退款时只统计已成功金额，多个处理中退款可以累计超过支付金额；因此保留基本的处理中金额占用，但不做自动收敛。
2. **售后申请锁定 `order_items` 行**  
   如果不同幂等键并发申请同一订单明细，只靠普通查询会出现多个活跃售后；因此保留明细行锁。

---

## 1. 仓库实际状态

### 1.1 Git

```text
当前分支: feature/product-inventory
HEAD:     7619066
远程:     origin/feature/product-inventory 已同步
main:     3292b85
```

TASK-003.2～003.5 的代码在功能分支上，尚未合并到 `main`。

### 1.2 已有代码

```text
TASK-001 基础设施：存在
TASK-002 认证：存在
TASK-003.2 商品/库存模型与迁移：存在
TASK-003.3 分类：存在
TASK-003.4 商品与 SKU：存在
TASK-003.5 库存四类操作与流水：存在
TASK-004 订单/支付/售后：不存在
```

当前库存流水类型 CHECK 已允许 7 种：

```text
INITIAL, STOCK_IN, RESERVE, RELEASE,
RESERVED_OUTBOUND, DIRECT_OUTBOUND, ADJUSTMENT
```

但 `InventoryService` 目前只实现：

```text
INITIAL, STOCK_IN, DIRECT_OUTBOUND, ADJUSTMENT
```

`RESERVE` / `RELEASE` / `RESERVED_OUTBOUND` 需要 TASK-004 扩展。

### 1.3 数据库

```text
Alembic head: c851e383d3fe
表:
  alembic_version
  categories
  inventory
  inventory_transactions
  products
  refresh_sessions
  skus
  users
```

没有订单、支付、退款、售后表。测试数据当前为 0 行。

### 1.4 现有可复用能力

- `CurrentUser` / `CurrentAdmin`；
- `transaction_context`；
- 统一异常响应；
- Inventory 双维度库存与流水；
- 条件 UPDATE + `FOR UPDATE`；
- 真实 MySQL 集成测试基础设施。

### 1.5 需要扩展的点

| 位置 | 现状 | TASK-004 需要 |
|---|---|---|
| `InventoryRepository` | 只更新 `total_quantity` | 双维度 total/reserved 条件更新 |
| `InventoryService` | 无 reserve/release/reserved_outbound | 新增订单库存原语 |
| `InventoryTransactionRepository.create` | 未接收业务 ID | 写入 `business_id` / `business_item_id` |
| 库存 Service 死锁处理 | 单操作回滚 session | 订单外层事务由 OrderService 控制 |
| `tests/test_migrations.py` | 硬编码 parent | 新迁移后更新断言 |

---

## 2. 第一版范围

### 2.1 必须实现

#### 订单

- 创建、查询、取消；
- 商品和 SKU 快照；
- 服务端计算金额；
- 订单创建幂等；
- 状态流转；
- 管理员发货、送达、完成。

#### 库存

- 下单预占；
- 取消释放；
- 支付成功扣减预占；
- 退货入库；
- 换货补发出库；
- 事务、行锁、条件更新；
- 库存流水和基本幂等。

#### 支付

- MOCK 支付；
- 支付宝电脑网站支付沙箱；
- 异步回调验签和金额校验；
- 回调幂等；
- 防止重复回调重复扣库存；
- 支付创建、取消、回调的基本状态一致性；
- `return_url` 不作为支付成功依据；
- 生产禁用 MOCK。

#### 退款

- 基本退款资格和金额校验；
- 退款金额不超过实际支付；
- 基本幂等；
- 成功/失败基本状态；
- 失败允许基本重试；
- MOCK 为主要自动化测试方式；
- 支付宝沙箱以全额退款验证为主。

#### 售后

- `REFUND_ONLY`；
- `RETURN_REFUND`；
- `EXCHANGE`（同 SKU）；
- 申请、审核、取消、退货物流、管理员收货；
- 售后申请基本幂等；
- 同一订单明细不能重复创建活跃售后；
- 售后库存操作正确。

#### 权限与安全

- 用户只能操作自己的订单、支付和售后；
- 管理端接口必须管理员权限；
- API 使用业务编号，不暴露自增 ID；
- 金额使用 `Decimal`；
- 密钥通过环境变量配置。

### 2.2 第一版不做

- 完整多笔成功支付对账与自动恢复；
- 复杂 STOCK_ERROR 多事务竞争恢复；
- 完整支付异常自动补偿和自动对账；
- 退款未知状态自动收敛；
- 极端理论竞争窗口的专项恢复体系；
- 过度细分的支付/退款/对账状态；
- 复杂死锁重试框架；
- 不同 SKU 换货、补差价；
- 部分数量退货/换货；
- 运费、优惠券、税费、发票；
- 售后凭证文件上传。

### 2.3 简化后的异常原则

无法安全自动处理的异常：

1. 事务整体回滚；
2. 记录 critical/error 日志和必要上下文；
3. 返回明确的 409/422 或让支付宝重试；
4. 由管理员通过后台或数据库运维处理；
5. 不在第一版建设自动修复流水线。

---

## 3. 核心业务规则

### 3.1 订单

- 订单快照保存商品名、SKU 编码、规格、单价、数量、行金额。
- 金额由服务端按 SKU 当前价格计算，不使用客户端金额。
- 金额使用 `Decimal`，数据库 `DECIMAL(12,2)`。
- 第一版不实现优惠券、运费、税费、发票。
- 订单创建必须携带收货人、电话、地址快照。
- 订单创建必须携带客户端幂等键。
- 订单号全局唯一，不暴露自增 ID。
- 用户只能查询/取消自己的订单；管理员可查询全部。
- 待支付订单可取消；已支付订单不能直接取消，只能退款/售后。
- 支付超时默认 30 分钟，可配置。
- 超时关闭由 CLI/cron 或管理员手动触发，不引入 Celery/MQ。

### 3.2 发货

- 订单保存：
  - `shipping_carrier`
  - `tracking_no`
  - `shipped_at`
  - `delivered_at`
  - `fulfillment_status`
- 管理员发货时必须同时填写承运商和运单号。
- 流程：
  - `UNSHIPPED → SHIPPED`：管理员发货；
  - `SHIPPED → DELIVERED`：管理员确认送达；
  - `DELIVERED → COMPLETED`：管理员完成订单。
- 未发货退款只允许 `UNSHIPPED` 状态。
- 退货退款/换货只允许已送达订单。

### 3.3 库存

| 场景 | 流水类型 | total_delta | reserved_delta |
|---|---|---:|---:|
| 下单 | `RESERVE` | 0 | +N |
| 取消/超时 | `RELEASE` | 0 | -N |
| 支付成功 | `RESERVED_OUTBOUND` | -N | -N |
| 退货入库 | `STOCK_IN` | +N | 0 |
| 未发货退款回补 | `STOCK_IN` | +N | 0 |
| 换货补发 | `DIRECT_OUTBOUND` | -N | 0 |

规则：

- 订单创建只预占，不扣总库存；
- 支付成功才把预占转成扣减；
- 取消/超时释放预占；
- 不允许负库存或 `reserved > total`；
- 多 SKU 按 `sku_id` 升序；
- 任一 SKU 失败，订单事务整体回滚；
- 订单流水写 `business_type='ORDER'`、`business_id=order_id`、`business_item_id=order_item_id`；
- 释放/扣减前按订单明细汇总净预占，不能只看库存总预留。

### 3.4 支付

- 支持 `MOCK` 和 `ALIPAY`。
- **一个订单只创建一个支付单**，`payments.order_id` 唯一。
- 支付创建：
  - 订单不存在支付单：创建 `PENDING`；
  - 已存在：直接返回已有支付单（幂等）；
  - 已失败/关闭：第一版不自动重建支付单，订单取消后重新下单。
- 支付成功依据：
  - 支付宝异步通知 `notify_url`；
  - 服务端主动查询 `alipay.trade.query`；
  - 不以 `return_url` 为准。
- 支付成功必须校验：
  - 验签；
  - `app_id`；
  - `seller_id`；
  - `out_trade_no`；
  - `total_amount`；
  - `trade_status`。
- 支付回调必须幂等。
- 同一支付单重复成功回调：
  - 返回 `success`；
  - 不重复扣库存；
  - 不重复改变订单状态。
- 支付成功时，库存扣减、支付单更新和订单更新在同一个事务中完成。
- 库存扣减失败：
  - 整个回调事务回滚；
  - 记录 critical 日志；
  - 返回 failure；
  - 不做 STOCK_ERROR 自动恢复，等待支付宝重试或管理员处理。

### 3.5 晚到支付

- 订单取消/关闭后仍收到支付成功通知：
  - 支付单记录 `SUCCESS`；
  - `exception_reason='LATE_PAYMENT'`；
  - 订单保持 `CLOSED`/`CANCELLED`；
  - 不恢复订单、不预占、不扣库存；
  - 返回 `success` 停止支付宝重试；
  - 管理员通过手动退款处理。
- 不实现多笔成功支付对账或自动退款。

### 3.6 退款

- 退款资格：支付单 `SUCCESS` 或部分退款状态。
- 退款金额不能超过：
  - 支付金额；
  - 减去已成功退款；
  - 减去 `PENDING`/`PROCESSING` 退款占用。
- 退款记录创建和额度校验在支付单 `FOR UPDATE` 锁内完成。
- 退款状态：
  - `PENDING`：已创建，占用额度；
  - `PROCESSING`：外部处理中/未知，继续占用；
  - `SUCCESS`：成功；
  - `FAILED`：失败，释放额度。
- `FAILED` 可手动重试，复用同一退款单号和 `out_request_no`。
- `PROCESSING` 超时/结果未知：
  - 继续占用额度；
  - 不创建新退款；
  - 管理员查询或重试同一退款；
  - 不做自动收敛。
- 同一支付单可以有多笔退款，但每笔必须不同幂等键。
- 同一售后单只对应一笔退款。
- 售后整行退款金额 = `order_item.line_amount`。
- 未发货退款：退款成功后回补库存。
- 退货退款：管理员确认收货时回补库存，退款成功不重复回补。
- 晚到支付退款：不回补库存。
- 退款成功/失败与售后状态更新在同一事务中完成。

### 3.7 售后

- 支持 `REFUND_ONLY`、`RETURN_REFUND`、`EXCHANGE`。
- 第一版整行售后：`quantity = order_item.quantity`。
- 期限：
  - `REFUND_ONLY`：从 `paid_at` 起连续 7×24 小时（默认，可配置）；
  - `RETURN_REFUND`：从 `delivered_at` 起连续 7×24 小时（默认，可配置）；
  - `EXCHANGE`：从 `delivered_at` 起连续 7×24 小时（默认，可配置）。
- 期限计算：
  - 服务端/数据库统一 UTC；
  - 7 天 = 168 小时，不是自然日；
  - `now <= deadline` 允许，`now > deadline` 拒绝；
  - `paid_at` 取自主支付成功时间（本版只有一个支付单，取该支付成功时间）。
- `REFUND_ONLY`：支付成功、`UNSHIPPED`、订单未关闭/取消；
- `RETURN_REFUND` / `EXCHANGE`：支付成功、`DELIVERED`。
- 同一订单明细同时只能有一个未结束售后。
- 换货第一版只允许同 SKU。
- 退货物流由用户填写承运商/运单号。
- 管理员确认收货后：
  - 退货退款：入库 + 创建退款；
  - 换货：入库，等待补发。
- 换货补发时出库，售后完成。
- 售后状态与退款状态分别维护。

### 3.8 时间、权限与编号

- 时间统一 UTC，数据库 `DATETIME(6)`。
- 金额使用 `Decimal`，序列化为字符串。
- 用户接口使用 `CurrentUser`，管理端使用 `CurrentAdmin`。
- API 使用：
  - `order_no`
  - `after_sales_no`
  - `payment_no`
  - `refund_no`
- API 响应不返回数据库自增 `id`。

---

## 4. 数据模型

### 4.1 `orders`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | BIGINT PK | 主键 |
| `order_no` | VARCHAR(32) ASCII | 唯一订单号 |
| `user_id` | BIGINT FK users | 用户 |
| `status` | VARCHAR(24) | PENDING_PAYMENT/PAID/CANCELLED/CLOSED/COMPLETED |
| `payment_status` | VARCHAR(24) | UNPAID/PAID/PARTIALLY_REFUNDED/REFUNDED |
| `fulfillment_status` | VARCHAR(24) | UNSHIPPED/SHIPPED/DELIVERED |
| `total_amount` | DECIMAL(12,2) | 商品总额 |
| `paid_amount` | DECIMAL(12,2) | 已支付 |
| `refunded_amount` | DECIMAL(12,2) | 已退款 |
| `currency` | CHAR(3) | CNY |
| `receiver_name` | VARCHAR(64) | 收货人 |
| `receiver_phone` | VARCHAR(32) | 电话 |
| `receiver_address` | VARCHAR(500) | 地址 |
| `customer_remark` | VARCHAR(255) | 备注 |
| `idempotency_key` | VARCHAR(128) ASCII | 下单幂等键 |
| `expires_at` | DATETIME(6) | 支付截止 |
| `paid_at` | DATETIME(6) | 支付成功时间 |
| `shipped_at` | DATETIME(6) | 发货时间 |
| `delivered_at` | DATETIME(6) | 送达时间 |
| `completed_at` | DATETIME(6) | 完成时间 |
| `cancelled_at` | DATETIME(6) | 取消时间 |
| `closed_at` | DATETIME(6) | 关闭时间 |
| `cancel_reason` / `close_reason` | VARCHAR(255) | 原因 |
| `shipping_carrier` | VARCHAR(64) | 承运商 |
| `tracking_no` | VARCHAR(64) | 运单号 |
| `created_at` / `updated_at` | DATETIME(6) | 时间 |

约束/索引：

```text
UNIQUE(order_no)
UNIQUE(user_id, idempotency_key)
INDEX(user_id, created_at)
INDEX(status, expires_at)
INDEX(created_at)
INDEX(tracking_no)
CHECK(total_amount > 0)
CHECK(paid_amount >= 0 AND paid_amount <= total_amount)
CHECK(refunded_amount >= 0 AND refunded_amount <= paid_amount)
CHECK(
  (shipping_carrier IS NULL AND tracking_no IS NULL)
  OR
  (shipping_carrier IS NOT NULL AND tracking_no IS NOT NULL)
)
```

### 4.2 `order_items`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | BIGINT PK | 主键，作为 `business_item_id` |
| `order_id` | BIGINT FK orders | 订单 |
| `product_id` | BIGINT FK products | 商品 |
| `sku_id` | BIGINT FK skus | SKU |
| `product_no` | VARCHAR(32) | 快照 |
| `product_name` | VARCHAR(200) | 快照 |
| `sku_code` | VARCHAR(64) | 快照 |
| `sku_attributes` | JSON | 规格快照 |
| `currency` | CHAR(3) | CNY |
| `unit_price` | DECIMAL(12,2) | 单价 |
| `quantity` | INT | 数量 |
| `line_amount` | DECIMAL(12,2) | 行金额 |
| `created_at` | DATETIME(6) | 时间 |

约束/索引：

```text
UNIQUE(order_id, sku_id)
INDEX(sku_id)
INDEX(product_id)
CHECK(quantity > 0)
CHECK(unit_price > 0)
CHECK(line_amount > 0)
```

### 4.3 `payments`

一个订单最多一个支付单。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | BIGINT PK | 主键 |
| `payment_no` | VARCHAR(32) ASCII | 支付单号 |
| `order_id` | BIGINT FK orders | 订单，唯一 |
| `user_id` | BIGINT FK users | 用户 |
| `channel` | VARCHAR(16) | MOCK/ALIPAY |
| `amount` | DECIMAL(12,2) | 支付金额 |
| `status` | VARCHAR(24) | PENDING/SUCCESS/FAILED/CLOSED/PARTIALLY_REFUNDED/REFUNDED |
| `provider_trade_no` | VARCHAR(64) | 支付宝交易号 |
| `refunded_amount` | DECIMAL(12,2) | 已成功退款 |
| `exception_reason` | VARCHAR(64) | 可选：LATE_PAYMENT 等人工关注标记 |
| `failure_code` / `failure_message` | VARCHAR(255) | 失败信息 |
| `paid_at` | DATETIME(6) | 支付成功时间 |
| `closed_at` | DATETIME(6) | 关闭时间 |
| `created_at` / `updated_at` | DATETIME(6) | 时间 |

约束/索引：

```text
UNIQUE(payment_no)
UNIQUE(order_id)
UNIQUE(channel, provider_trade_no)   -- nullable
INDEX(order_id, status)
INDEX(status, created_at)
CHECK(amount > 0)
CHECK(refunded_amount >= 0 AND refunded_amount <= amount)
```

说明：

- 一个订单只有一个支付单；
- 不设置 `is_primary`、`DUPLICATE_PAYMENT`、`reconciliation_status`；
- 支付失败/关闭时，第一版不自动重建支付单；
- `exception_reason` 只用于晚到支付等需要人工关注的简单标记，不构成完整对账体系。

### 4.4 `refunds`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | BIGINT PK | 主键 |
| `refund_no` | VARCHAR(32) ASCII | 退款单号 |
| `order_id` | BIGINT FK orders | 订单 |
| `payment_id` | BIGINT FK payments | 支付单 |
| `after_sales_id` | BIGINT FK after_sales NULL | 售后单 |
| `user_id` | BIGINT FK users | 用户 |
| `amount` | DECIMAL(12,2) | 退款金额 |
| `reason` | VARCHAR(255) | 原因 |
| `channel` | VARCHAR(16) | MOCK/ALIPAY |
| `status` | VARCHAR(24) | PENDING/PROCESSING/SUCCESS/FAILED |
| `provider_refund_no` | VARCHAR(64) | 支付宝退款单号 |
| `idempotency_key` | VARCHAR(128) ASCII | 退款幂等键 |
| `failure_code` / `failure_message` | VARCHAR(255) | 失败信息 |
| `requested_at` / `processed_at` | DATETIME(6) | 时间 |
| `created_at` / `updated_at` | DATETIME(6) | 时间 |

约束/索引：

```text
UNIQUE(refund_no)
UNIQUE(payment_id, idempotency_key)
UNIQUE(after_sales_id)        -- nullable
INDEX(order_id, status)
INDEX(payment_id, status)
CHECK(amount > 0)
```

额度规则：

- `PENDING`、`PROCESSING`、`SUCCESS` 占用额度；
- `FAILED` 释放额度；
- 不设置 `CLOSED` 状态，避免多一种终态；
- 额度校验和退款创建在支付单锁内完成。

### 4.5 `after_sales`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | BIGINT PK | 主键 |
| `after_sales_no` | VARCHAR(32) | 售后单号 |
| `order_id` | BIGINT FK orders | 订单 |
| `order_item_id` | BIGINT FK order_items | 明细 |
| `user_id` | BIGINT FK users | 用户 |
| `type` | VARCHAR(24) | REFUND_ONLY/RETURN_REFUND/EXCHANGE |
| `status` | VARCHAR(32) | 见状态机 |
| `quantity` | INT | 数量 |
| `requested_amount` | DECIMAL(12,2) | 申请金额 |
| `approved_amount` | DECIMAL(12,2) NULL | 审核金额 |
| `reason` | VARCHAR(255) | 原因 |
| `description` | TEXT | 描述 |
| `evidence_urls` | JSON NULL | 凭证 URL |
| `review_note` | VARCHAR(500) | 审核备注 |
| `reviewed_by` | BIGINT FK users NULL | 审核人 |
| `reviewed_at` | DATETIME(6) | 审核时间 |
| `return_carrier` / `return_tracking_no` | VARCHAR(64) | 退货物流 |
| `returned_at` | DATETIME(6) | 寄回时间 |
| `received_by` | BIGINT FK users NULL | 收货人 |
| `received_at` | DATETIME(6) | 收货时间 |
| `replacement_carrier` / `replacement_tracking_no` | VARCHAR(64) | 换货补发 |
| `replacement_shipped_at` | DATETIME(6) | 补发时间 |
| `completed_at` / `cancelled_at` | DATETIME(6) | 时间 |
| `idempotency_key` | VARCHAR(128) ASCII | 申请幂等键 |
| `created_at` / `updated_at` | DATETIME(6) | 时间 |

约束/索引：

```text
UNIQUE(after_sales_no)
UNIQUE(user_id, idempotency_key)
INDEX(user_id, status)
INDEX(order_id)
INDEX(order_item_id, status)
INDEX(status, created_at)
CHECK(quantity > 0)
CHECK(requested_amount > 0)
CHECK(approved_amount IS NULL OR approved_amount <= requested_amount)
```

说明：

- 不设置 `REPLACEMENT_PENDING`；换货收货后保持 `RECEIVED`，补发完成直接 `COMPLETED`；
- `REFUND_FAILED` 保留，用于显示需要管理员重试的售后；
- 退款状态与售后状态仍然分离。

### 4.6 `inventory_transactions`

不修改表结构。TASK-004 写入：

| 场景 | type | total_delta | reserved_delta | business_type | business_id | business_item_id |
|---|---|---:|---:|---|---|---|
| 下单 | RESERVE | 0 | +N | ORDER | order_id | order_item_id |
| 取消/超时 | RELEASE | 0 | -N | ORDER | order_id | order_item_id |
| 支付成功 | RESERVED_OUTBOUND | -N | -N | ORDER | order_id | order_item_id |
| 退货入库 | STOCK_IN | +N | 0 | AFTER_SALE | after_sales_id | order_item_id |
| 未发货退款入库 | STOCK_IN | +N | 0 | REFUND | refund_id | order_item_id |
| 换货补发 | DIRECT_OUTBOUND | -N | 0 | AFTER_SALE | after_sales_id | order_item_id |

不增加 `business_item_id → order_items.id` 外键，保留多业务类型共用的可空引用和现有复合索引。

### 4.7 迁移

新增一个迁移，`down_revision = c851e383d3fe`，创建顺序：

```text
orders
→ order_items
→ payments
→ after_sales
→ refunds
```

更新 `tests/test_migrations.py` 的 parent 断言。

---

## 5. API 设计

### 5.1 用户端

全部要求 `CurrentUser`。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/orders` | 创建订单并预占库存 |
| GET | `/api/v1/orders` | 我的订单 |
| GET | `/api/v1/orders/{order_no}` | 我的订单详情 |
| POST | `/api/v1/orders/{order_no}/cancel` | 取消待支付订单 |
| POST | `/api/v1/orders/{order_no}/payments` | 创建或获取支付单 |
| GET | `/api/v1/payments/{payment_no}` | 查询自己的支付 |
| POST | `/api/v1/payments/{payment_no}/mock-success` | 模拟成功，仅开发/测试 |
| POST | `/api/v1/payments/{payment_no}/mock-fail` | 模拟失败，仅开发/测试 |
| POST | `/api/v1/orders/{order_no}/after-sales` | 申请售后 |
| GET | `/api/v1/orders/{order_no}/after-sales` | 我的售后 |
| GET | `/api/v1/after-sales/{after_sales_no}` | 售后详情 |
| POST | `/api/v1/after-sales/{after_sales_no}/cancel` | 取消售后 |
| POST | `/api/v1/after-sales/{after_sales_no}/return-shipment` | 填写退货物流 |

### 5.2 支付回调

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/payments/alipay/notify` | 验签回调，返回 `success`/`failure` |
| GET | `/api/v1/payments/alipay/return` | 同步跳回，不改变状态 |

### 5.3 管理端

全部要求 `CurrentAdmin`。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/admin/orders` | 订单列表 |
| GET | `/api/v1/admin/orders/{order_no}` | 订单详情 |
| POST | `/api/v1/admin/orders/{order_no}/ship` | 发货，要求承运商/运单号 |
| POST | `/api/v1/admin/orders/{order_no}/deliver` | 确认送达 |
| POST | `/api/v1/admin/orders/{order_no}/complete` | 完成订单 |
| POST | `/api/v1/admin/orders/close-expired` | 关闭过期订单 |
| GET | `/api/v1/admin/payments` | 支付列表 |
| GET | `/api/v1/admin/payments/{payment_no}` | 支付详情 |
| POST | `/api/v1/admin/payments/{payment_no}/sync` | 主动查询支付宝状态 |
| POST | `/api/v1/admin/refunds` | 手动退款（含晚到支付） |
| GET | `/api/v1/admin/refunds` | 退款列表 |
| GET | `/api/v1/admin/refunds/{refund_no}` | 退款详情 |
| POST | `/api/v1/admin/refunds/{refund_no}/retry` | 重试失败退款 |
| GET | `/api/v1/admin/after-sales` | 售后列表 |
| GET | `/api/v1/admin/after-sales/{after_sales_no}` | 售后详情 |
| POST | `/api/v1/admin/after-sales/{after_sales_no}/approve` | 审核通过 |
| POST | `/api/v1/admin/after-sales/{after_sales_no}/reject` | 审核拒绝 |
| POST | `/api/v1/admin/after-sales/{after_sales_no}/receive` | 确认收货 |
| POST | `/api/v1/admin/after-sales/{after_sales_no}/complete-exchange` | 换货补发完成 |

### 5.4 请求/响应示例

订单创建：

```json
{
  "items": [{"sku_code": "SKU001", "quantity": 2}],
  "idempotency_key": "order-create-uuid",
  "receiver_name": "张三",
  "receiver_phone": "13800000000",
  "receiver_address": "上海市..."
}
```

订单响应：

```text
order_no, status, payment_status, fulfillment_status,
total_amount, paid_amount, refunded_amount,
shipping_carrier, tracking_no,
receiver_name, receiver_phone, receiver_address,
items, expires_at, paid_at, shipped_at, delivered_at
```

支付创建：

```json
{"channel": "ALIPAY"}
```

响应：

```text
payment_no, status, amount, pay_url
```

售后申请：

```json
{
  "order_no": "ORD...",
  "sku_code": "SKU001",
  "type": "REFUND_ONLY",
  "reason": "不想要了",
  "description": "未发货退款",
  "idempotency_key": "after-sales-uuid"
}
```

管理端手动退款：

```json
{
  "payment_no": "PAY...",
  "amount": "199.80",
  "reason": "LATE_PAYMENT",
  "idempotency_key": "refund-uuid"
}
```

### 5.5 主要错误码

```text
ORDER_NOT_FOUND
ORDER_STATUS_CONFLICT
ORDER_EXPIRED
INSUFFICIENT_STOCK
ORDER_ITEM_RESERVATION_MISMATCH
IDEMPOTENCY_KEY_CONFLICT
PAYMENT_NOT_FOUND
PAYMENT_AMOUNT_MISMATCH
PAYMENT_NOT_RETRYABLE
INVALID_ALIPAY_SIGNATURE
ALIPAY_NOT_CONFIGURED
REFUND_NOT_FOUND
REFUND_AMOUNT_EXCEEDED
REFUND_NOT_ALLOWED
REFUND_STATUS_CONFLICT
AFTER_SALES_NOT_FOUND
AFTER_SALES_NOT_ALLOWED
AFTER_SALES_STATUS_CONFLICT
AFTER_SALES_ALREADY_EXISTS
AFTER_SALES_EXPIRED
RETURN_NOT_ALLOWED
PERMISSION_DENIED
```

---

## 6. 状态机

### 6.1 订单

```text
PENDING_PAYMENT
  ├── PAID
  ├── CANCELLED
  └── CLOSED

PAID
  └── COMPLETED
```

### 6.2 订单支付汇总

```text
UNPAID
  └── PAID
        ├── PARTIALLY_REFUNDED
        └── REFUNDED

PARTIALLY_REFUNDED
  └── REFUNDED
```

`PAID` 可以直接转 `REFUNDED`，不要求经过 `PARTIALLY_REFUNDED`。

### 6.3 支付单

```text
PENDING
  ├── SUCCESS
  ├── FAILED
  └── CLOSED

SUCCESS
  ├── PARTIALLY_REFUNDED
  └── REFUNDED
```

### 6.4 履约

```text
UNSHIPPED → SHIPPED → DELIVERED → COMPLETED
```

### 6.5 售后

```text
PENDING_REVIEW
  ├── APPROVED
  ├── REJECTED
  └── CANCELLED

APPROVED + REFUND_ONLY
  └── REFUNDING
        ├── COMPLETED
        └── REFUND_FAILED
              └── REFUNDING（重试）

APPROVED + RETURN_REFUND / EXCHANGE
  └── WAITING_RETURN
        └── RETURN_SHIPPED
              └── RECEIVED
                    ├── RETURN_REFUND → REFUNDING → COMPLETED / REFUND_FAILED
                    └── EXCHANGE → 补发 → COMPLETED
```

### 6.6 退款

```text
PENDING → PROCESSING → SUCCESS
                    └── FAILED → PROCESSING（重试）
```

---

## 7. 事务、锁与幂等

### 7.1 统一锁顺序

```text
orders
  → order_items
  → payments
  → after_sales
  → refunds
  → inventory（按 sku_id 升序）
```

同类多行按主键升序。不使用的表可以跳过，但不能反向获取锁。

### 7.2 订单创建

```text
BEGIN
  幂等查询
  锁 products（id 升序）
  锁 skus（id 升序）
  校验商品/SKU/库存
  INSERT orders
  INSERT order_items（flush 获取 item_id）
  FOR item ORDER BY sku_id:
    UPDATE inventory
      SET reserved_quantity = reserved_quantity + qty
      WHERE sku_id = ?
        AND total_quantity - reserved_quantity >= qty
    rowcount 必须为 1
    INSERT inventory_transactions (RESERVE)
COMMIT
```

任一失败整体回滚。

### 7.3 订单取消

```text
BEGIN
  SELECT order FOR UPDATE
  校验 PENDING_PAYMENT
  FOR item ORDER BY sku_id:
    UPDATE inventory SET reserved_quantity = reserved_quantity - qty
      WHERE sku_id = ? AND reserved_quantity >= qty
    rowcount 必须为 1
    INSERT inventory_transactions (RELEASE)
  UPDATE payments
    SET status='CLOSED', closed_at=UTC_TIMESTAMP(6)
    WHERE order_id=? AND status='PENDING'
  UPDATE orders SET status='CANCELLED', cancelled_at=UTC_TIMESTAMP(6)
COMMIT
```

提交后：

- 尽力调用支付宝关闭接口；
- 外部关闭失败只记录日志，不回滚本地取消；
- 后续成功回调按晚到支付规则处理。

### 7.4 支付成功

```text
BEGIN
  SELECT order FOR UPDATE
  SELECT payment FOR UPDATE
  校验验签、金额、app_id、seller_id、trade_status
  IF payment 已 SUCCESS: 幂等返回
  IF order CLOSED/CANCELLED:
     payment = SUCCESS
     payment.exception_reason = LATE_PAYMENT
     不改变订单、不改变库存
  ELSE IF order PENDING_PAYMENT:
     FOR item ORDER BY sku_id:
       校验明细净预占
       UPDATE inventory
         SET total_quantity = total_quantity - qty,
             reserved_quantity = reserved_quantity - qty
         WHERE sku_id = ?
           AND reserved_quantity >= qty
           AND total_quantity >= qty
       INSERT inventory_transactions (RESERVED_OUTBOUND)
     payment = SUCCESS
     order = PAID
     order.payment_status = PAID
     order.paid_at = payment.paid_at
     order.paid_amount = payment.amount
COMMIT
```

库存扣减失败时：

- 整单事务回滚；
- 记录 critical 日志；
- 返回 failure；
- 不自动创建 STOCK_ERROR 状态，不执行额外恢复事务；
- 等待支付宝重试或管理员处理。

### 7.5 退款额度

```text
BEGIN
  SELECT order FOR UPDATE
  SELECT order_item FOR UPDATE（如关联售后）
  SELECT payment FOR UPDATE
  SELECT after_sales FOR UPDATE（如关联）
  SELECT refund FOR UPDATE（同幂等键重试）

  IF 幂等键已存在:
     指纹一致：返回原退款
     指纹不一致：409

  已占用 =
    SUM(refunds.amount)
    WHERE payment_id = ?
      AND status IN ('PENDING', 'PROCESSING', 'SUCCESS')

  IF 已占用 + 本次退款金额 > payment.amount:
      409 REFUND_AMOUNT_EXCEEDED

  INSERT refund (status='PENDING')
COMMIT
```

外部退款调用在事务外；提交后置 `PROCESSING`；结果未知时继续占用额度，管理员重试/查询，不自动收敛。

### 7.6 售后申请

```text
1. 快速路径按 (user_id, idempotency_key) 查询
   - 同指纹：返回原售后单
   - 不同指纹：409 IDEMPOTENCY_KEY_CONFLICT
2. BEGIN
3. 锁 order FOR UPDATE
4. 锁 order_item FOR UPDATE
5. 锁后重查幂等键
6. 查询该明细其他活跃售后
   - 存在：409 AFTER_SALES_ALREADY_EXISTS
7. 校验类型、期限、订单状态、金额
8. INSERT after_sales
9. COMMIT
```

请求指纹：

```text
order_no / sku_code / type / quantity / reason / description / evidence_urls
```

### 7.7 幂等键

| 实体 | 唯一约束 |
|---|---|
| `orders` | `(user_id, idempotency_key)` |
| `payments` | 一个订单一个支付单，`UNIQUE(order_id)` |
| `refunds` | `(payment_id, idempotency_key)` |
| `after_sales` | `(user_id, idempotency_key)` |
| `inventory_transactions` | `idempotency_key` 全局唯一 |

库存流水键：

```text
order:{order_id}:line:{order_item_id}:reserve
order:{order_id}:line:{order_item_id}:release
order:{order_id}:line:{order_item_id}:ship
after_sale:{after_sales_id}:return-restock
after_sale:{after_sales_id}:exchange-outbound
refund:{refund_id}:restock
```

### 7.8 死锁处理

- 捕获 MySQL 1213/1205；
- 最多做一次有界重试，或返回 409；
- 不做复杂重试框架；
- 所有重试依赖幂等键。

### 7.9 外部调用

- 支付宝 page pay、query、refund、close 在事务外调用；
- 不持有库存行锁等待网络；
- 外部结果未知时保留处理中状态，人工/定时查询；
- 不做自动收敛流水线。

---

## 8. 支付宝沙箱

### 8.1 能力

- 电脑网站支付支持沙箱；
- 使用沙箱 APPID、RSA2 密钥、支付宝公钥；
- 沙箱主要支持 Android 客户端和余额支付；
- 沙箱与生产不完全一致。

### 8.2 `alipay.trade.page.pay`

- 页面跳转接口；
- 必填 `out_trade_no`、`total_amount`、`subject`、`product_code=FAST_INSTANT_TRADE_PAY`；
- 支持 `notify_url`、`return_url`、`time_expire`；
- `return_url` 不是支付成功依据。

### 8.3 异步通知

- POST 表单；
- 去除 `sign`、`sign_type` 后验签；
- 校验 `out_trade_no`、`total_amount`、`seller_id`、`app_id`；
- 只有 `TRADE_SUCCESS` / `TRADE_FINISHED` 算支付成功；
- 返回 `success`；
- 未收到通知用 `alipay.trade.query` 补偿。

### 8.4 退款

- `alipay.trade.refund`；
- 传 `out_trade_no`、`refund_amount`、稳定的 `out_request_no`；
- `code=10000` 不等于退款成功，必须检查 `fund_change=Y`；
- `fund_change=N` 或缺失时查询退款；
- 失败重试复用同一退款单号；
- 支付宝沙箱第一版以全额退款验证为主；
- 部分退款不纳入沙箱硬性验收。

### 8.5 网关与 SDK

- 沙箱网关以当前沙箱控制台为准，不硬编码；
- 官方 Python SDK 需在 TASK-004.6 前确认兼容性；
- 不在设计阶段安装依赖。

---

## 9. 测试方案

### 9.1 订单

- 创建、查询、取消；
- 快照和金额；
- 多 SKU 预留；
- 库存不足整体回滚；
- 订单幂等；
- 用户隔离；
- 管理员查询；
- 发货/送达/完成；
- 取消关闭支付、释放库存；
- 已支付不可直接取消；
- 过期关闭；
- 公开编号路径。

### 9.2 库存

- reserve/release/reserved_outbound；
- 单 SKU 并发不超卖；
- 多 SKU 原子性；
- 明细净预占校验；
- 库存流水正确；
- 幂等重复请求不重复变更。

### 9.3 支付

- MOCK 成功/失败；
- 支付回调重复不重复扣库存；
- 金额/签名/app_id/seller_id 校验；
- 订单 PAID 与库存扣减一致；
- 取消与回调竞争；
- 晚到支付记录 `LATE_PAYMENT` 且不恢复订单；
- `return_url` 不改变状态；
- 支付查询补偿。

### 9.4 退款

- MOCK 成功/失败；
- 金额不超过可退款额度；
- 同一支付多笔退款额度正确；
- 重复退款幂等；
- PENDING/PROCESSING 占用额度；
- FAILED 释放额度；
- 退款与订单/支付/售后状态一致；
- 晚到支付退款不回补库存。

### 9.5 售后

- 三类售后；
- 审核/拒绝/取消；
- 退货物流/收货；
- 退货入库；
- 换货入库/补发；
- 三类售后期限及边界；
- 同键同指纹返回原单；
- 同键异指纹冲突；
- 异键活跃售后冲突；
- 并发申请只成功一条；
- 权限隔离。

### 9.6 权限与质量

- 未登录 401；
- 普通用户 403；
- 管理员接口 GET 也需要管理员；
- 用户不能访问他人订单/支付/售后；
- Decimal 金额；
- 公开编号不暴露自增 ID。

真实 MySQL 集成测试用于事务、行锁、并发和幂等；支付宝使用 fake client/单测，沙箱手工验收不纳入 CI。

---

## 10. TASK-004.2～004.9 验收标准

### TASK-004.2 数据模型与迁移

- 创建 `orders`、`order_items`、`payments`、`refunds`、`after_sales`；
- `payments.order_id` 唯一；
- `orders` 包含 shipping 字段；
- `refunds` 包含 PENDING/PROCESSING/SUCCESS/FAILED；
- 幂等唯一约束按范围建立；
- Alembic upgrade/downgrade/upgrade；
- `alembic check`；
- 更新迁移测试；
- 不实现 API。

### TASK-004.3 库存订单原语

- total/reserved 双维度条件更新；
- reserve/release/reserved_outbound；
- 退货入库/换货出库；
- business_id/business_item_id；
- 明细净预占校验；
- 基本并发/幂等测试；
- 不创建订单 API。

### TASK-004.4 订单核心

- 创建、列表、详情、取消；
- 快照、金额、用户隔离；
- 发货/送达/完成；
- `shipping_carrier`、`tracking_no` 必填；
- 订单幂等；
- 多 SKU 原子性；
- 过期关闭服务；
- 公开路径使用 `order_no`。

### TASK-004.5 MOCK 支付

- 一个订单一个支付单；
- MOCK success/fail；
- 支付成功扣减预占；
- 重复回调幂等；
- 取消/支付竞争；
- 晚到支付基本标记；
- 生产禁用 MOCK；
- 不实现多笔支付对账。

### TASK-004.6 支付宝沙箱

- 配置/密钥；
- page pay；
- notify 验签/金额/字段校验；
- 回调幂等；
- query 补偿；
- return 页面；
- 晚到支付基本处理；
- 沙箱全额退款验证；
- 不把 return_url 当成功依据。

### TASK-004.7 退款

- 退款模型/API；
- MOCK 退款；
- 支付宝退款；
- 金额校验包含 PENDING/PROCESSING；
- 支付单锁内原子创建；
- 失败重试；
- 退款与售后一致；
- 晚到支付退款；
- 不做自动未知状态收敛。

### TASK-004.8 售后

- 三类售后；
- 申请锁 order_item；
- 同键幂等返回原单；
- 异键活跃售后拒绝；
- 审核/取消/物流/收货；
- 退货入库；
- 换货入库/补发；
- 三类期限；
- 权限隔离；
- 并发申请测试。

### TASK-004.9 管理端与质量收口

- 管理端订单/支付/退款/售后；
- 公开编号；
- 关闭过期订单；
- 权限测试；
- 全量回归；
- Ruff/Mypy/format；
- 交付报告。

---

## 11. 延期与人工处理

明确延期到后续版本：

1. 多笔成功支付对账与自动退款；
2. STOCK_ERROR 自动恢复/修复库存接口；
3. 支付异常自动补偿和自动对账；
4. 退款未知状态自动收敛；
5. 复杂死锁重试框架；
6. 部分数量退货/换货；
7. 不同 SKU 换货/补差价；
8. 运费、优惠券、税费、发票；
9. 售后凭证文件上传；
10. 支付失败后自动重建支付单。

第一版遇到无法安全自动处理的异常：

- 回滚事务；
- 记录 critical/error 日志；
- 返回明确错误或让支付宝重试；
- 由管理员人工处理；
- 不自动修复、不掩盖异常。

---

## 12. 预计开发范围

与上一版相比，第一版减少：

- `is_primary`、`DUPLICATE_PAYMENT`、多支付对账；
- STOCK_ERROR 独立恢复和 repair API；
- 退款未知状态自动收敛；
- `REPLACEMENT_PENDING` 等细分状态；
- 多笔支付/重复支付/STOCK_ERROR 专项并发测试；
- 复杂支付对账字段和错误码。

仍保留：

- 5 张新表；
- 订单、库存、支付、退款、售后主流程；
- 事务、行锁、条件更新、幂等、权限；
- 基本并发测试；
- 支付宝沙箱适配。

范围明显降低，但仍能覆盖真实电商核心业务和面试需要解释的事务/并发/幂等能力，符合项目目标。

---

## 13. 本次执行边界

本次只修改设计文档：

- 不修改业务代码；
- 不修改模型；
- 不创建/修改迁移；
- 不修改测试；
- 不安装依赖；
- 不执行 Git commit；
- 不开始 TASK-004.2。

等待 ChatGPT Review 和用户确认后再进入实现阶段。
