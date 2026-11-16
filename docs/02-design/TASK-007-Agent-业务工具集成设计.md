# TASK-007 Agent 与电商业务集成设计

> 文档类型：TASK-007 详细设计  
> 所属阶段：V1.2 第二阶段——AI 能力建设  
> 前置任务：TASK-001～TASK-006  
> 文档状态：第一版设计基线，待仓库核对与正式冻结  
> 适用范围：TASK-007.1～TASK-007.6  
> 设计依据：V1.2 项目总体规划、系统总体架构、AI Agent 总体设计、TASK-004.1 订单支付售后设计、TASK-005 RAG 详细设计、TASK-006 LangGraph Agent 核心设计

---

# 1. 设计目标

TASK-006 已经完成通用 Agent 核心，当前系统具备：

- 普通对话；
- 意图识别；
- LangGraph 工作流；
- RAG 知识检索；
- Redis 多轮会话；
- 用户身份隔离；
- Guardrails；
- Agent Chat API。

但目前 Agent 不能真正调用电商业务能力。

TASK-007 的目标是让 Agent 能够在认证用户的权限范围内，调用已有电商业务 Service。

完成后，用户可以通过自然语言完成：

1. 搜索商品；
2. 查询商品详情；
3. 查询 SKU；
4. 查询库存；
5. 查询自己的订单；
6. 查询订单详情；
7. 取消符合条件的待支付订单；
8. 查询自己的售后记录；
9. 申请符合业务规则的售后。

核心原则：

**Agent 负责理解和编排，Tool 负责受控调用，Service 负责最终业务规则和权限校验。**

# 2. 项目范围

## 2.1 本次实现

| 模块          | 功能                                      |
| ------------- | ----------------------------------------- |
| Tool 基础设施 | Tool Registry、Tool Schema、Tool Executor |
| 商品查询      | 商品搜索、商品详情                        |
| SKU 查询      | SKU 详情、规格                            |
| 库存查询      | SKU 可用库存                              |
| 订单查询      | 我的订单、订单详情                        |
| 订单取消      | 待支付订单取消                            |
| 售后查询      | 我的售后列表、售后详情                    |
| 售后申请      | REFUND_ONLY、RETURN_REFUND、EXCHANGE      |
| 操作确认      | Prepare / Confirm                         |
| Agent 集成    | LangGraph Tool Calling                    |
| 安全控制      | 身份隔离、权限、参数校验、幂等、防重放    |
| 自动化测试    | 单元测试、集成测试、并发和安全测试        |

## 2.2 本次不实现

- 创建订单；
- 发起支付；
- 支付宝操作；
- 直接退款；
- 管理员退款；
- 管理员售后审核；
- 管理员发货；
- 管理员库存调整；
- 管理员订单管理；
- 修改用户资料；
- 修改收货地址；
- 商品上下架；
- 库存写入；
- 多 Agent 协作；
- 自主执行复杂多步骤业务计划；
- 新增前端页面；
- 微服务；
- MQ、Kafka、Celery；
- Kubernetes。

第一版只实现普通认证用户的业务操作。

即使当前登录用户是管理员，也不因为 `is_admin=True` 自动获得 Agent 管理端操作能力。

# 3. 总体架构

## 3.1 核心调用链

```text
用户
 │
 ▼
POST /api/v1/agent/chat
 │
 ▼
CurrentUser
 │
 ▼
AgentRuntime
 │
 ▼
LangGraph Agent
 │
 ▼
LLM 意图识别与 Tool Calling
 │
 ▼
Tool Registry
 │
 ▼
Tool Executor
 │
 ▼
Tool Adapter
 │
 ▼
业务 Service
 │
 ▼
Repository
 │
 ▼
MySQL
```

涉及高风险写操作时：

```text
用户请求取消订单/申请售后
          │
          ▼
Agent 调用 Prepare Tool
          │
          ▼
后端检查操作资格
          │
          ▼
生成一次性 confirmation_id
          │
          ▼
Redis 保存待确认操作
          │
          ▼
返回操作摘要
          │
          ▼
用户明确确认
          │
          ▼
POST /api/v1/agent/actions/{confirmation_id}/confirm
          │
          ▼
后端验证用户、操作、参数、有效期
          │
          ▼
原子消费 confirmation_id
          │
          ▼
重新执行 Service 权限与业务校验
          │
          ▼
业务事务提交
          │
          ▼
返回执行结果
```

## 3.2 架构约束

必须保持：

```text
Agent
  → Tool
    → Service
      → Repository
        → Database
```

严格禁止：

1. Agent 直接访问数据库。
2. Tool 直接调用 Repository。
3. Tool 自行编写订单、库存、售后的业务规则。
4. LLM 自行决定用户身份或权限。
5. 通过 Prompt 判断是否有权限。
6. 客户端传入 user_id 决定数据归属。
7. LLM 直接执行高风险写操作。
8. 用户只在聊天中说“好的”，后端就自动执行写操作。

Service 是业务规则和权限的最终执行边界。

# 4. Tool 基础设施设计

## 4.1 Tool Registry

新增统一 Tool Registry。

职责：

- 注册允许 Agent 使用的 Tool；
- 管理 Tool 名称和描述；
- 管理 Tool 参数 Schema；
- 区分 READ 和 PREPARE 类型；
- 提供允许调用的 Tool 白名单；
- 阻止模型调用未注册 Tool。

建议模块组织：

```text
app/agent/tools/
├── __init__.py
├── registry.py
├── executor.py
├── schemas.py
├── context.py
├── errors.py
├── product.py
├── inventory.py
├── order.py
├── after_sales.py
└── confirmation.py
```

实际目录可以根据当前仓库结构微调，但不得改变模块职责。

## 4.2 Tool 分类

第一版只允许两类 Tool：

| 类型    | 说明                       | 是否直接产生业务副作用 |
| ------- | -------------------------- | ---------------------- |
| READ    | 查询商品、库存、订单和售后 | 否                     |
| PREPARE | 准备订单取消或售后申请     | 否                     |

真正的写操作只能通过独立 Confirm API 执行。

不向 LLM 暴露直接执行写操作的 Tool。

## 4.3 Tool Context

Tool 不接受模型传入的用户身份。

统一从 AgentRuntimeContext 获取：

```python
class AgentToolContext:
    user: User
    session: AsyncSession
    settings: Settings
    request_id: str
    conversation_id: str
```

具体类型和字段以当前 TASK-006 RuntimeContext 为准，不要重复建立第二套用户上下文体系。

Tool 不接受以下参数：

```text
user_id
is_admin
role
session
database_url
api_key
```

用户身份始终由 FastAPI 的 `CurrentUser` 提供。

## 4.4 Tool 参数校验

所有 Tool 参数必须使用 Pydantic v2 Schema。

要求：

- `extra="forbid"`；
- 限制字符串长度；
- 限制分页范围；
- Enum 限制业务类型；
- 不允许传数据库自增 ID；
- 不允许传用户身份；
- 不允许传内部权限字段；
- 不允许传任意 SQL 或 Repository 参数。

所有外部业务对象使用公开业务编号：

- `product_no`
- `sku_code`
- `order_no`
- `after_sales_no`

不向 LLM 暴露数据库内部 ID。

# 5. 商品、SKU 与库存 Tool

## 5.1 商品搜索

Tool：

```text
search_products
```

输入：

```json
{
  "query": "iPhone 17",
  "page": 1,
  "page_size": 10
}
```

要求：

- 只查询允许公开展示的商品；
- 不返回下架或不可见商品；
- 分页；
- 限制最大 page_size；
- 搜索条件经过 Schema 校验。

返回：

```json
{
  "items": [
    {
      "product_no": "P10001",
      "name": "商品名称",
      "description": "商品简介",
      "status": "ACTIVE",
      "price_range": {
        "min": "5999.00",
        "max": "6999.00",
        "currency": "CNY"
      }
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 10
}
```

价格由数据库业务数据提供，不允许模型自行编造。

## 5.2 商品详情

Tool：

```text
get_product_detail
```

输入：

```json
{
  "product_no": "P10001"
}
```

返回：

- 商品编号；
- 商品名称；
- 商品描述；
- 分类；
- 商品状态；
- SKU 列表；
- 价格信息。

不返回数据库内部 ID。

## 5.3 SKU 详情

Tool：

```text
get_sku_detail
```

输入：

```json
{
  "sku_code": "SKU001"
}
```

返回：

- SKU 编码；
- 商品名称；
- 规格属性；
- SKU 价格；
- SKU 状态。

## 5.4 库存查询

Tool：

```text
check_sku_inventory
```

输入：

```json
{
  "sku_code": "SKU001"
}
```

返回：

```json
{
  "sku_code": "SKU001",
  "available_quantity": 25,
  "stock_status": "IN_STOCK"
}
```

库存可用数量由服务端计算：

```text
available_quantity = total_quantity - reserved_quantity
```

不向普通用户暴露不必要的内部预留库存明细。

Tool 只读，不允许修改库存。

# 6. 订单查询 Tool

## 6.1 查询我的订单

Tool：

```text
list_my_orders
```

输入：

```json
{
  "status": "PENDING_PAYMENT",
  "page": 1,
  "page_size": 10
}
```

其中 status 可选。

订单数据必须通过当前认证用户过滤。

不能因为模型传入其他用户订单编号就允许访问。

返回：

```json
{
  "items": [
    {
      "order_no": "ORD20260001",
      "status": "PENDING_PAYMENT",
      "payment_status": "UNPAID",
      "fulfillment_status": "UNSHIPPED",
      "total_amount": "199.00",
      "currency": "CNY",
      "created_at": "2026-11-16T10:00:00"
    }
  ],
  "total": 1
}
```

## 6.2 查询订单详情

Tool：

```text
get_my_order
```

输入：

```json
{
  "order_no": "ORD20260001"
}
```

返回：

- 订单编号；
- 订单状态；
- 支付状态；
- 履约状态；
- 商品明细；
- 数量；
- 金额；
- 创建时间；
- 支付时间；
- 发货时间；
- 送达时间；
- 承运商；
- 运单号；
- 主支付对账状态（适用时）。

只能查询当前用户自己的订单。

不返回数据库内部 ID、支付密钥或无关个人敏感数据。

# 7. 售后查询 Tool

## 7.1 查询我的售后列表

Tool：

```text
list_my_after_sales
```

输入：

```json
{
  "order_no": "ORD20260001",
  "page": 1,
  "page_size": 10
}
```

`order_no` 可选。

## 7.2 查询售后详情

Tool：

```text
get_my_after_sales
```

输入：

```json
{
  "after_sales_no": "AS20260001"
}
```

返回：

- 售后单号；
- 订单号；
- SKU 编码；
- 售后类型；
- 售后状态；
- 申请原因；
- 申请金额；
- 审核金额；
- 退货物流；
- 换货物流；
- 创建时间；
- 完成时间。

必须校验售后单归属当前用户。

# 8. 高风险操作确认设计

## 8.1 基本原则

订单取消和售后申请属于写操作。

采用：

```text
Prepare → User Confirm → Execute
```

严禁：

```text
LLM → 直接写数据库
```

也严禁：

```text
LLM → 直接调用业务 Service 执行写操作
```

## 8.2 Prepare 阶段

Agent 只能调用 Prepare Tool：

```text
prepare_cancel_order
prepare_create_after_sales
```

Prepare 阶段：

1. 获取当前认证用户；
2. 查询目标业务对象；
3. 检查当前操作是否具备基本资格；
4. 生成操作摘要；
5. 生成随机 confirmation_id；
6. 生成 nonce；
7. 计算规范化参数 SHA-256；
8. 保存待确认记录；
9. 设置有效期；
10. 返回待确认信息。

Prepare 阶段不得：

- 取消订单；
- 释放库存；
- 创建售后单；
- 创建退款单；
- 修改支付状态；
- 修改库存。

## 8.3 Confirmation 记录

第一版使用现有 Redis，不新增数据库表。

Redis Key：

```text
agent:action:confirmation:{confirmation_id}
```

建议记录：

```json
{
  "user_id": 1001,
  "conversation_id": "uuid",
  "action_type": "CANCEL_ORDER",
  "tool_name": "prepare_cancel_order",
  "resource_id": "ORD20260001",
  "arguments": {
    "order_no": "ORD20260001",
    "reason": "用户主动取消"
  },
  "arguments_hash": "sha256...",
  "nonce": "random...",
  "status": "PREPARED",
  "created_at": "2026-11-16T10:00:00",
  "expires_at": "2026-11-16T10:05:00"
}
```

要求：

- confirmation_id 使用密码学安全随机数生成；
- 不允许使用递增 ID；
- 记录绑定 user_id；
- 记录绑定 conversation_id；
- 记录绑定 action_type；
- 记录绑定资源编号；
- 记录绑定完整规范化参数哈希；
- 记录 nonce；
- 记录过期时间；
- 默认有效期 300 秒，可配置；
- Redis Key 设置相同 TTL；
- 不允许客户端修改待确认参数。

confirmation_id 应作为不透明的一次性凭据使用，不向日志输出。

## 8.4 Confirm 阶段

接口：

```text
POST /api/v1/agent/actions/{confirmation_id}/confirm
```

必须使用：

```python
CurrentUser
```

确认接口不接收订单号、SKU、金额、售后类型等业务参数。

所有待执行参数从 Redis 服务端记录读取。

确认流程：

1. 获取当前 CurrentUser；
2. 根据 confirmation_id 获取待确认记录；
3. 校验 user_id；
4. 校验 conversation_id 关联；
5. 校验 action_type；
6. 校验 arguments_hash；
7. 校验 nonce；
8. 校验有效期；
9. 使用 Lua 原子消费 confirmation_id；
10. 调用对应的业务 Service；
11. Service 在事务内重新校验业务权限、状态和操作资格；
12. 返回真实业务执行结果。

确认凭据只能消费一次。

错误情况：

| 情况           | 处理             |
| -------------- | ---------------- |
| 不存在         | 404              |
| 不属于当前用户 | 404 或统一拒绝   |
| 已过期         | 409              |
| 已消费         | 409              |
| 参数校验不一致 | 409              |
| 业务状态已变化 | 返回对应业务冲突 |
| Redis 不可用   | 503              |

不得把确认凭据失效解释为业务操作已经失败或成功；以业务查询结果为准。

## 8.5 原子消费与业务幂等

Redis Lua 必须保证：

- 检查确认记录；
- 检查用户绑定；
- 检查有效期；
- 检查 PREPARED 状态；
- 原子改变状态或消费凭据。

不得先检查再通过另一条独立命令删除。

业务 Service 仍然必须保证幂等和事务安全。

售后申请使用服务端生成的稳定幂等键，关联本次 confirmation_id，并复用 TASK-004 已有的售后幂等约束。

订单取消必须依赖订单行锁、状态复验和同一事务内的库存 RELEASE，确保重复请求不会重复释放库存。

如果确认凭据已经消费但请求结果不确定，用户应通过订单/售后查询 Tool 获取真实业务状态；不得盲目重复执行。

## 8.6 用户明确确认

聊天中的“好的”“确认”等自然语言不能直接触发写操作。

必须通过独立 Confirm API。

后续前端通过明确的确认交互调用该接口。

确认摘要必须由后端根据真实业务数据构造，不能完全依赖 LLM 生成。

# 9. 订单取消 Tool

Tool：

```text
prepare_cancel_order
```

输入：

```json
{
  "order_no": "ORD20260001",
  "reason": "用户主动取消"
}
```

## 9.1 业务限制

严格遵循 TASK-004.1：

- 只能取消当前用户自己的订单；
- 订单必须为 `PENDING_PAYMENT`；
- 已支付订单不能直接取消；
- 已发货订单不能直接取消；
- 订单已关闭或取消时不能重复释放库存。

已支付订单需要根据情况申请售后，不能通过订单取消绕过退款和售后规则。

## 9.2 Confirm 后的业务流程

必须复用现有 OrderService。

业务事务：

```text
BEGIN

SELECT order FOR UPDATE

校验订单归属
校验 PENDING_PAYMENT

FOR item ORDER BY sku_id:

    释放该订单明细的库存预占

    写入 RELEASE 库存流水

更新订单状态：

    status = CANCELLED
    cancelled_at = now()

COMMIT
```

遵循 TASK-004.1 已冻结的锁顺序和库存规则。

不得由 Agent Tool 自己执行上述数据库操作。

## 9.3 确认摘要

示例：

```json
{
  "action": "CANCEL_ORDER",
  "order_no": "ORD20260001",
  "order_status": "PENDING_PAYMENT",
  "reason": "用户主动取消",
  "effect": "取消订单并释放预占库存",
  "confirmation_required": true
}
```

只有用户明确调用 Confirm API 后才执行。

# 10. 售后申请 Tool

Tool：

```text
prepare_create_after_sales
```

输入：

```json
{
  "order_no": "ORD20260001",
  "sku_code": "SKU001",
  "type": "REFUND_ONLY",
  "reason": "商品不再需要",
  "description": "尚未发货，希望申请退款"
}
```

不接受客户端或模型传入：

- user_id；
- order_item_id；
- after_sales_id；
- requested_amount；
- approved_amount；
- 数据库内部 ID；
- 任意库存数量。

## 10.1 售后类型

只支持：

```text
REFUND_ONLY
RETURN_REFUND
EXCHANGE
```

严格遵循 TASK-004.1 的已冻结业务规则。

### REFUND_ONLY

必须满足：

- 支付成功；
- `fulfillment_status = UNSHIPPED`；
- 订单未关闭或取消；
- 同一订单明细不存在活跃售后。

TASK-004.1 中 REFUND_ONLY 申请期限起算时间曾被明确标记为待确认。

因此第一版不得擅自添加 7 天限制，实际规则必须复用已完成的 AfterSalesService。

### RETURN_REFUND

必须满足：

- 支付成功；
- 订单已送达；
- 在 `delivered_at + 7 天` 内；
- 同一订单明细不存在活跃售后。

### EXCHANGE

必须满足：

- 支付成功；
- 订单已送达；
- 在 `delivered_at + 7 天` 内；
- 同一订单明细不存在活跃售后；
- 第一版只允许同 SKU 换货。

## 10.2 售后申请范围

第一版按订单明细整行申请：

```text
quantity = order_item.quantity
```

不支持部分数量售后。

申请金额由后端从订单明细快照计算：

```text
requested_amount = order_item.line_amount
```

不得让 LLM 决定金额。

## 10.3 Confirm 后的执行

复用现有 AfterSalesService。

必须在 Service 事务中：

1. 锁定订单；
2. 锁定订单明细；
3. 校验用户归属；
4. 校验支付和履约状态；
5. 校验售后期限；
6. 锁后检查活跃售后；
7. 创建售后记录；
8. 写入服务端生成的幂等键；
9. 提交事务。

售后申请成功后，状态应为：

```text
PENDING_REVIEW
```

这只表示售后申请已经提交，不表示审核通过，也不表示退款成功。

## 10.4 重要边界

Agent 不得：

- 自动审核售后；
- 自动创建退款单；
- 自动执行退款；
- 自动确认退货收货；
- 自动执行换货补发。

退款、售后审核、退货收货和换货补发仍然由 TASK-004 既有业务流程控制。

# 11. LangGraph Tool Calling 集成

## 11.1 Graph 扩展

保留 TASK-006 现有 Graph，不重新实现。

新增受控 Tool Calling 流程：

```text
START
  │
  ▼
load_conversation
  │
  ▼
classify_intent
  │
  ▼
route_intent
  ├── general_answer
  ├── retrieve_knowledge
  ├── business_tool_planning
  └── unsupported_action

business_tool_planning
  │
  ▼
LLM Tool Calling
  │
  ▼
validate_tool_call
  │
  ▼
tool_executor
  ├── READ Tool
  │      │
  │      ▼
  │   tool_result
  │      │
  │      ▼
  │   LLM final_answer
  │
  └── PREPARE Tool
         │
         ▼
      pending_confirmation
         │
         ▼
      返回确认摘要
```

## 11.2 Tool 执行次数

第一版每次用户请求最多执行 4 次 Tool 调用。

超过上限停止工具循环，并返回可理解的提示。

配置：

```text
agent_max_tool_calls_per_turn = 4
```

不允许无限循环。

## 11.3 Tool Calling 规则

- 只允许注册过的 Tool；
- 参数必须通过 Pydantic 校验；
- Tool 返回结果必须经过统一序列化；
- Tool 错误不能伪装为成功；
- Tool 输出中的商品描述等文本仍然是不可信数据；
- 模型不得修改后端权限判断；
- 不允许工具调用工具之外的任意 Python 函数；
- 不允许动态导入或动态执行代码；
- 不允许模型调用不存在的 Tool。

PREPARE Tool 执行后必须停止当前写操作链路，等待用户通过 Confirm API 确认。

确认接口不经过 LLM Tool Calling。

# 12. Agent API 设计

## 12.1 聊天接口

复用：

```text
POST /api/v1/agent/chat
```

请求：

```json
{
  "conversation_id": "uuid",
  "message": "帮我查一下我的订单 ORD20260001"
}
```

响应：

```json
{
  "conversation_id": "uuid",
  "message_id": "uuid",
  "answer": "你的订单当前处于待支付状态。",
  "sources": [],
  "pending_action": null,
  "created_at": "2026-11-16T10:00:00Z"
}
```

## 12.2 待确认操作响应

当 Agent 准备取消订单：

```json
{
  "conversation_id": "uuid",
  "message_id": "uuid",
  "answer": "订单符合取消条件，请确认是否取消。",
  "sources": [],
  "pending_action": {
    "confirmation_id": "opaque-random-token",
    "nonce": "opaque-nonce",
    "conversation_id": "uuid",
    "action_type": "CANCEL_ORDER",
    "title": "取消订单",
    "resource_no": "ORD20260001",
    "effect": "取消订单并释放预占库存",
    "expires_at": "2026-11-16T10:05:00Z"
  },
  "created_at": "2026-11-16T10:00:00Z"
}
```

确认摘要中只包含后端已经验证的业务数据。

## 12.3 确认接口

```text
POST /api/v1/agent/actions/{confirmation_id}/confirm
```

请求：

```json
{
  "conversation_id": "uuid",
  "nonce": "opaque-nonce"
}
```

要求：

- 必须认证；
- 使用 CurrentUser；
- 不接受客户端重新提交业务参数；
- 不通过 LLM 再次判断是否执行；
- 读取 Redis 中的原始准备记录；
- 校验用户和操作绑定；
- 原子消费确认凭据；
- 重新调用业务 Service。

成功响应：

```json
{
  "success": true,
  "action_type": "CANCEL_ORDER",
  "resource_no": "ORD20260001",
  "message": "订单已成功取消。"
}
```

业务失败返回统一错误结构。

# 13. 异常处理

至少统一处理以下情况：

| 错误                                | 含义               |
| ----------------------------------- | ------------------ |
| AGENT_TOOL_NOT_FOUND                | Tool 不存在        |
| AGENT_TOOL_ARGUMENT_INVALID         | Tool 参数不合法    |
| AGENT_TOOL_LIMIT_EXCEEDED           | Tool 调用次数超限  |
| AGENT_ACTION_CONFIRMATION_NOT_FOUND | 确认记录不存在     |
| AGENT_ACTION_CONFIRMATION_EXPIRED   | 确认已过期         |
| AGENT_ACTION_CONFIRMATION_CONSUMED  | 确认凭据已使用     |
| AGENT_ACTION_CONFIRMATION_MISMATCH  | 用户或参数不匹配   |
| AGENT_ACTION_NOT_ALLOWED            | 当前业务不允许操作 |
| AGENT_BUSINESS_OPERATION_FAILED     | 业务执行失败       |

业务原有错误码继续复用，例如：

```text
ORDER_NOT_FOUND
ORDER_STATUS_CONFLICT
AFTER_SALES_NOT_FOUND
AFTER_SALES_NOT_ALLOWED
AFTER_SALES_STATUS_CONFLICT
PERMISSION_DENIED
IDEMPOTENCY_KEY_CONFLICT
```

不重复发明一套订单或售后错误体系。

不向用户返回数据库异常、SQL、内部堆栈或密钥。

# 14. 日志与安全审计

记录：

- request_id；
- user_id；
- conversation_id；
- tool_name；
- resource_no；
- tool 类型；
- 执行结果；
- 业务错误码；
- 执行耗时；
- confirmation_id 的安全摘要或不可逆标识。

禁止记录：

- API Key；
- JWT；
- 完整 confirmation 凭据；
- 密码；
- 完整 Prompt；
- 用户完整聊天历史；
- 不必要的收货地址、手机号；
- 完整售后描述和凭证内容。

写操作的业务结果以订单、售后等真实业务数据为准，日志不能代替业务记录。

# 15. 配置设计

仅在确有需要时新增配置。

建议：

```text
agent_max_tool_calls_per_turn = 4
agent_action_confirmation_ttl_seconds = 300
```

已有配置继续复用：

```text
agent_max_execution_seconds
agent_rate_limit_per_minute
agent_llm_timeout_seconds
agent_llm_max_retries
```

新增配置同步更新：

```text
app/core/config.py
.env.example
```

不重复创建配置体系。

# 16. 测试设计

## 16.1 Tool Registry

- 注册 Tool；
- 获取 Tool；
- 未注册 Tool 拒绝；
- 重复注册拒绝；
- Tool 参数校验；
- 禁止额外字段；
- 禁止客户端传入 user_id；
- Tool 调用次数限制。

## 16.2 商品与库存

- 商品搜索；
- 商品详情；
- SKU 查询；
- 库存查询；
- 下架商品不可作为正常可售商品返回；
- 不暴露内部 ID；
- 不允许 Tool 修改库存。

## 16.3 订单查询

- 查询当前用户订单；
- 查询订单详情；
- 查询其他用户订单；
- 伪造 user_id；
- 不存在订单；
- 分页和状态过滤。

## 16.4 售后查询

- 查询我的售后；
- 查询售后详情；
- 查询其他用户售后；
- 不存在售后；
- 终结状态正确返回。

## 16.5 订单取消

- 待支付订单可以 Prepare；
- 已支付订单不能取消；
- 已发货订单不能取消；
- 已取消订单不能重复释放库存；
- Prepare 不修改订单；
- 未确认不能取消；
- 确认成功后订单变为 CANCELLED；
- 库存预占正确释放；
- RELEASE 库存流水正确；
- 并发取消不会重复释放库存；
- 其他用户不能取消该订单。

## 16.6 售后申请

- REFUND_ONLY 未发货申请；
- RETURN_REFUND 已送达申请；
- EXCHANGE 已送达申请；
- 送达超过 7 天拒绝；
- 未支付拒绝；
- 同一明细已有活跃售后拒绝；
- 同一明细并发申请只能成功一个；
- 数量必须为整行数量；
- 金额由后端计算；
- 未确认不创建售后；
- 确认后状态为 PENDING_REVIEW；
- 不自动创建退款；
- 其他用户不能申请。

## 16.7 Confirm 安全

- 正常确认；
- 错误用户确认；
- 过期确认；
- 重放确认；
- 并发重复确认；
- 修改资源编号；
- 修改参数；
- 修改售后类型；
- 修改金额；
- nonce 不匹配；
- Redis 异常；
- 确认期间订单状态变化；
- 确认凭据只能消费一次。

## 16.8 Graph 集成

- 普通对话不调用 Tool；
- 商品查询正确调用商品 Tool；
- 库存查询正确调用库存 Tool；
- 订单查询正确调用订单 Tool；
- 取消订单只产生 Prepare；
- 售后申请只产生 Prepare；
- Tool 失败时模型不声称成功；
- 多 Tool 调用次数限制；
- 恶意商品描述不能改变 Tool 权限；
- RAG 与业务 Tool 可以在同一 Agent 中协作；
- 普通用户无法调用管理员操作。

# 17. 子任务划分

TASK-007 仍然是原路线中的一个顶层任务，不新增顶层 TASK。

内部拆分如下：

| 子任务     | 内容                                         |
| ---------- | -------------------------------------------- |
| TASK-007.1 | 仓库核查、Tool 契约、Registry 和执行基础设施 |
| TASK-007.2 | 商品、SKU、库存只读 Tool                     |
| TASK-007.3 | 订单和售后只读 Tool                          |
| TASK-007.4 | Prepare / Confirm 高风险操作确认机制         |
| TASK-007.5 | 订单取消、售后申请写 Tool 和 LangGraph 集成  |
| TASK-007.6 | 安全测试、集成测试、回归和交付               |

执行顺序：

```text
007.1
  ↓
007.2
  ↓
007.3
  ↓
007.4
  ↓
007.5
  ↓
007.6
```

每个子任务内部完成必要测试后继续下一个，不需要每次等待人工确认。

# 18. 验收标准

TASK-007 完成必须满足：

1. Tool Registry 可用；
2. Tool Schema 参数校验有效；
3. Agent 可以搜索商品；
4. Agent 可以查询商品详情和 SKU；
5. Agent 可以查询可用库存；
6. Agent 可以查询当前用户订单；
7. Agent 可以查询订单详情；
8. Agent 可以查询当前用户售后；
9. Agent 可以准备取消待支付订单；
10. 未确认时不产生任何写操作；
11. 用户明确确认后可以取消订单；
12. 库存释放和库存流水正确；
13. Agent 可以准备申请售后；
14. 用户明确确认后创建售后记录；
15. 售后状态正确为 PENDING_REVIEW；
16. 售后申请不自动退款；
17. 不同用户之间数据隔离；
18. 确认凭据防重放；
19. 写操作遵循 Service 业务规则；
20. Agent 不直接访问 Repository 或数据库；
21. TASK-005 RAG 功能不受影响；
22. TASK-006 原有能力不受影响；
23. pytest 全量通过；
24. Ruff 通过；
25. Mypy 通过；
26. Alembic 检查通过；
27. Docker 构建和必要集成验证通过；
28. 提供完整交付报告；
29. 不擅自提交 Git；
30. 不进入 TASK-008。

# 19. 非目标与后续扩展

以下能力留待后续版本，不在本次实现：

- 创建订单；
- 发起支付；
- 直接退款；
- 管理员审核；
- 管理员发货；
- 管理员库存管理；
- SSE/WebSocket；
- 多 Agent；
- 自动规划复杂业务；
- 复杂审批工作流；
- 多租户；
- 分布式任务队列。

TASK-007 完成后，第一版 Agent 核心业务能力视为完成，后续进入前端建设与系统集成阶段。
