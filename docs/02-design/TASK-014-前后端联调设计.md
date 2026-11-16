# TASK-014 前后端集成设计

> 项目：E-Commerce Agent  
> 文档类型：TASK-014 详细设计  
> 文档状态：待评审，评审通过后实施  
> 所属阶段：Stage 4——集成与质量保障  
> 前置任务：TASK-001～013  
> 后续任务：TASK-015、TASK-016  
> 适用架构：模块化单体，单 FastAPI 服务  
> 当前代码结构：`backend/`、`agent/`、`frontend/`

---

## 1. 任务概述

### 1.1 任务背景

TASK-001～013 已完成 Backend、RAG、Agent 和 React 前端的独立开发。

目前已有：

- FastAPI 后端 API；
- JWT 认证和 Refresh Token Rotation；
- 商品、SKU、库存、订单、支付、售后业务；
- RAG 知识库管理与检索；
- LangGraph Agent；
- Agent 业务 Tool；
- 高风险操作 Prepare / Confirm；
- React 管理后台；
- Agent 对话和确认操作界面。

TASK-014 不重新开发这些功能，而是将现有前端与后端进行完整集成，检查真实 API 请求、响应、权限、异常和状态同步。

### 1.2 核心目标

1. React 前端能够正确调用真实 FastAPI API。
2. 认证状态、Token 刷新和退出登录流程可靠。
3. 所有核心业务页面使用真实后端数据。
4. 前后端字段、枚举、分页和错误结构一致。
5. Agent Chat、RAG、Tool、Prepare / Confirm 能够形成真实闭环。
6. 修复联调中发现的前后端契约问题。
7. 保持现有 API 路径和业务规则不变。

### 1.3 非目标

本任务不负责：

- 重新设计数据库；
- 修改订单、库存、支付、售后业务规则；
- 重新实现 Agent Graph；
- 重新实现 RAG；
- 增加新的业务模块；
- 重写 React 前端；
- 引入 WebSocket 或 SSE；
- 引入微服务；
- 生产服务器部署；
- 大规模 UI 美化。

---

## 2. 当前项目结构与运行关系

```text
E-commerce-agent/
│
├── backend/
│   └── app/
│       ├── api/
│       ├── core/
│       ├── models/
│       ├── repositories/
│       ├── schemas/
│       ├── services/
│       └── main.py
│
├── agent/
│   ├── graph.py
│   ├── nodes.py
│   ├── runtime.py
│   └── tools/
│
├── frontend/
│   ├── src/api/
│   ├── src/components/
│   ├── src/pages/
│   ├── src/router/
│   ├── src/stores/
│   └── src/types/
│
└── docker-compose.yml
```

运行关系：

```text
React Frontend
      │
      │ HTTP / JSON
      ▼
FastAPI Backend
      │
      ├── Authentication API
      ├── Product API
      ├── Inventory API
      ├── Order API
      ├── Payment API
      ├── After-Sales API
      ├── Knowledge API
      │
      └── Agent API Adapter
                │
                ▼
            Agent Runtime
                │
                ├── LangGraph
                ├── LLM
                ├── Tool Registry
                ├── Tool Executor
                └── RAG Retrieval
```

前端只与 FastAPI 通信，不直接连接 MySQL、Redis 或 Qdrant。

Agent 继续通过 Tool → Service 调用业务能力，不允许绕过 Service 直接访问 Repository 或数据库。

---

## 3. 前后端 API 契约

### 3.1 API 基础约定

统一使用现有 API 前缀：

```text
/api/v1
```

前端通过 Axios API Client 访问后端。

要求：

- 不在页面组件中直接拼接完整后端 URL。
- API 请求集中在 `frontend/src/api/`。
- 请求和响应类型集中在 `frontend/src/types/`。
- 页面通过 API 模块获取数据。
- 不使用生产环境 Mock 数据代替真实 API。
- 不允许前端自行推断后端业务状态。

### 3.2 认证 API

重点验证：

| 功能       | API                          |
| ---------- | ---------------------------- |
| 注册       | POST `/api/v1/auth/register` |
| 登录       | POST `/api/v1/auth/login`    |
| 当前用户   | GET `/api/v1/auth/me`        |
| 刷新 Token | POST `/api/v1/auth/refresh`  |
| 登出       | POST `/api/v1/auth/logout`   |

要求：

1. 登录成功后保存 Access Token 和 Refresh Token。
2. 需要认证的请求携带 Access Token。
3. Access Token 过期后按现有机制刷新。
4. 多个并发请求同时遇到 401 时，使用共享 Refresh Promise，避免并发刷新导致 Refresh Token Rotation 冲突。
5. 刷新失败后清理本地认证状态并跳转登录页。
6. 登出后清理本地 Token 和用户状态。
7. 不将用户身份交由前端自行决定。
8. 后端权限判断仍然以 CurrentUser / CurrentAdmin 为准。

特别验证：

- 正常登录；
- Access Token 过期；
- Refresh Token 有效；
- Refresh Token 失效；
- Refresh Token 重放；
- 普通用户访问管理员 API；
- 登出后再次访问受保护 API。

### 3.3 商品与 SKU

验证页面：

- 商品列表；
- 商品详情；
- 商品创建；
- 商品编辑；
- 商品上下架；
- 分类管理；
- SKU 管理；
- SKU 价格更新。

要求：

- SPU 与 SKU 的字段映射一致。
- 商品状态使用后端真实枚举。
- SKU 价格使用后端实际金额类型及序列化格式。
- 分类关系使用后端返回的数据。
- 商品列表刷新后显示真实结果。
- 商品详情中的 SKU 数据不能由前端模拟。

### 3.4 库存

验证页面：

- 库存查询；
- 入库；
- 库存调整；
- 库存流水。

要求：

1. 入库和调整调用真实库存 API。
2. 数量和原因字段与后端 Schema 一致。
3. 成功后刷新库存和流水。
4. 失败时显示后端错误信息。
5. 不允许前端直接修改库存展示值来假装操作成功。
6. 库存最终结果必须以后端数据库为准。

### 3.5 订单与支付

验证页面：

- 订单列表；
- 订单详情；
- 支付状态；
- 订单状态；
- 订单相关操作。

要求：

- 订单状态严格使用后端枚举。
- 支付状态以支付 API / 订单响应提供的权威数据为准。
- 不根据前端本地时间推断支付成功。
- 不伪造支付成功结果。
- 不把支付页面跳转成功等同于支付完成。
- 订单和支付关联字段如果后端未提供，前端不得自行猜测。

支付回调的真实性和沙箱完整验证属于 TASK-015。

### 3.6 售后

验证页面：

- 售后列表；
- 售后详情；
- 售后状态；
- 售后申请信息。

要求：

- 展示后端真实售后状态。
- 用户只能看到其有权访问的数据。
- 不由前端自行决定售后是否满足申请条件。
- 退款、审核等结果以后端业务处理为准。

当前没有实现的管理端审核、退款、发货等操作，不得在本任务中虚构出来。

### 3.7 知识库

验证页面：

- 知识库文档列表；
- 文档上传；
- 文档详情；
- 文档版本；
- 删除；
- 检索测试。

必须验证非空数据流程：

```text
上传文档
   ↓
Backend Document Service
   ↓
解析文件
   ↓
Chunk
   ↓
Embedding
   ↓
Qdrant
   ↓
发布
   ↓
Retrieval API
```

要求：

- 上传文件使用真实 API。
- 文件类型、大小、错误信息与后端限制一致。
- 上传成功后能看到真实文档状态。
- 文档版本正确显示。
- 检索结果中的来源信息来自后端。
- ADMIN_ONLY 权限不能由前端过滤来代替后端 ACL。

### 3.8 Agent Chat

验证页面：

`/agent`

请求：

```text
POST /api/v1/agent/chat
```

要求：

- 用户发送消息后调用真实 Agent API。
- conversation_id 正确传递和复用。
- 多轮会话上下文保持一致。
- RAG 来源由后端返回。
- Agent 错误能够显示为用户可理解的提示。
- 不在前端保存或构造 System Prompt。
- 不在前端伪造 Agent Tool 结果。
- 不将 LLM 原始异常堆栈暴露给用户。

必须验证：

1. 普通对话。
2. 多轮对话。
3. 知识库问答。
4. RAG 来源展示。
5. 商品查询 Tool。
6. 订单查询 Tool。
7. 未授权操作拒绝。
8. Agent 服务不可用时的错误展示。

### 3.9 Prepare / Confirm

必须完成完整交互：

```text
用户请求取消订单
       │
       ▼
Agent Prepare
       │
       ▼
返回 Pending Action
       │
       ▼
前端展示确认卡片
       │
       ▼
用户主动点击确认
       │
       ▼
Confirm API
       │
       ▼
后端原子消费确认凭证
       │
       ▼
OrderService
       │
       ▼
返回最终业务结果
```

要求：

- Pending Action 必须来自后端真实响应。
- 前端只展示确认信息。
- 用户必须主动点击确认。
- Confirm 请求只能发送后端约定的 conversation_id 和 nonce。
- 不允许前端提交新的订单状态或业务参数来覆盖 Prepare 内容。
- 成功后刷新订单状态。
- 失败后展示真实错误。
- 过期确认凭证应正确提示。
- 重复点击不能产生重复业务操作。
- 前端不得将按钮点击成功直接显示为业务成功。

取消订单以现有 TASK-007 确认机制和 OrderService 规则为准。

售后 Prepare / Confirm 也按现有实现验证，不新增自动退款、自动审核等功能。

---

## 4. 错误处理与状态同步

### 4.1 HTTP 状态码

重点覆盖：

| 状态码 | 前端处理                 |
| ------ | ------------------------ |
| 400    | 显示业务参数错误         |
| 401    | 按认证流程刷新或重新登录 |
| 403    | 显示权限不足             |
| 404    | 显示资源不存在           |
| 409    | 显示状态冲突或重复操作   |
| 422    | 显示参数校验错误         |
| 429    | 提示请求频率过高         |
| 500    | 显示通用服务器错误       |
| 503    | 显示服务暂不可用         |

错误响应应优先复用 Backend 已有异常结构，不要为了前端方便修改所有后端异常格式。

### 4.2 Loading / Empty / Error

所有数据页面必须覆盖：

- Loading：加载中。
- Empty：没有数据。
- Success：正常数据。
- Error：请求失败。

对于写操作：

- 防止重复提交；
- 显示执行状态；
- 成功后刷新真实数据；
- 失败后保留合理的用户输入；
- 不允许乐观更新造成错误业务状态。

### 4.3 TanStack Query

复用现有 Query 管理方式。

要求：

- 列表查询使用 Query。
- 写操作使用 Mutation。
- 成功后精确失效相关 Query Key。
- 不随意使用全局清缓存。
- 不在组件内重复实现复杂请求缓存。
- 不因刷新页面而丢失服务端业务状态。

---

## 5. CORS 与网络拓扑

当前开发环境使用 Vite Proxy。

TASK-014 继续采用现有代理，不为了开发方便随意开放生产 CORS。

开发请求：

```text
Browser
   │
   ▼
Vite Dev Server
   │ Proxy
   ▼
FastAPI
```

生产同源反向代理设计放在 TASK-016。

---

## 6. 实施阶段

### TASK-014.1：联调前检查

- 检查前端 API 模块。
- 检查 Backend API 路由。
- 检查 TypeScript 类型和 Pydantic Schema。
- 检查环境变量和代理配置。
- 建立接口契约清单。
- 标记已联调和未联调接口。

### TASK-014.2：认证与权限联调

- 注册、登录、当前用户。
- Token 刷新。
- 并发刷新。
- 登出。
- 管理员权限。
- 普通用户越权访问。

### TASK-014.3：核心业务联调

- 商品、SKU。
- 库存和流水。
- 订单和支付状态。
- 售后。

### TASK-014.4：RAG 联调

- 文档上传。
- 版本管理。
- 发布。
- 非空检索。
- ACL。
- 前端检索结果展示。

### TASK-014.5：Agent 联调

- 普通对话。
- RAG 问答。
- Tool 调用。
- Pending Action。
- Confirm。
- 失败与过期场景。

### TASK-014.6：整体回归

- 页面路由。
- 浏览器刷新。
- 登录状态。
- 错误提示。
- 数据刷新。
- 响应式基本检查。
- 完整后端和前端回归。

---

## 7. 测试策略

采用三层验证：

1. API 契约验证：前端请求和后端 Schema 一致。
2. 页面集成验证：页面真实调用 API，状态正确。
3. 业务链路验证：从页面操作到数据库最终状态完整正确。

测试数据使用独立测试账号和临时业务数据。

禁止：

- 使用生产用户数据测试；
- 将真实支付或真实退款作为普通联调操作；
- 直接修改数据库伪造成功结果；
- 在测试结束后遗留临时订单、库存或 Redis 确认凭证。

---

## 8. 验收标准

### 8.1 功能验收

- [ ] 注册、登录、登出正常。
- [ ] Access Token 刷新正常。
- [ ] 并发刷新没有 Refresh Token Rotation 冲突。
- [ ] 普通用户无法访问管理员接口。
- [ ] 商品和 SKU 页面真实数据正常。
- [ ] 库存操作和流水展示正常。
- [ ] 订单和支付状态展示正确。
- [ ] 售后数据展示正确。
- [ ] 知识库真实文档上传、发布和非空检索正常。
- [ ] Agent 普通对话正常。
- [ ] Agent RAG 来源展示正常。
- [ ] Agent Tool 调用正常。
- [ ] Prepare / Confirm 完整闭环正常。
- [ ] 过期和重复 Confirm 处理正确。
- [ ] 错误、空状态、Loading 状态正常。

### 8.2 质量验收

- [ ] 后端 pytest 全量通过。
- [ ] Ruff 通过。
- [ ] Mypy 通过。
- [ ] 前端 typecheck 通过。
- [ ] 前端 lint 通过。
- [ ] 前端 Vitest 通过。
- [ ] 前端 production build 通过。
- [ ] Docker 开发环境正常启动。
- [ ] 不新增非必要数据库迁移。
- [ ] 不修改既有业务规则。

### 8.3 交付物

- 前后端接口联调报告。
- API 契约问题及修复记录。
- 真实业务流程验证记录。
- Agent / RAG / Confirm 验证记录。
- 未解决问题清单。
- TASK-014 最终验收报告。

---

## 9. 风险与限制

1. Agent 真实调用依赖 DeepSeek API Key、网络和模型可用性。
2. RAG 非空检索依赖 BGE-M3 模型、Qdrant 和真实测试文档。
3. 支付真实沙箱回调完整性验证放在 TASK-015。
4. 前端 localStorage Token 存储存在 XSS 风险，应在 TASK-015 纳入安全评估，不在本任务随意改认证方案。
5. 当前 PaymentResponse 对订单关联信息的限制不得由前端猜测补齐。
6. 当前没有实现的管理端业务操作不得通过前端模拟。

---

## 10. 明确禁止

- 不修改订单、库存、支付、售后核心规则。
- 不修改 Agent Tool 权限边界。
- 不取消 Prepare / Confirm。
- 不让前端直接操作数据库。
- 不让 Agent 绕过 Tool 调用业务 Service。
- 不引入第二个 FastAPI 服务。
- 不引入 SSE / WebSocket。
- 不重构整个前端。
- 不升级依赖来解决无关问题。
- 不执行未经授权的 Git commit / push。

**TASK-014 完成定义：现有前端的核心业务能力全部通过真实后端 API 工作，Agent 和 RAG 也完成真实联调，而不是只通过 Mock 或单元测试。**
