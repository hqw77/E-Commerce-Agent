# 11 初级全栈面试速成执行手册

> 目标岗位：小公司初级全栈。
> 目标：不继续重构项目，用 3 天把现有项目讲到“能演示、能解释、能被追问”。
> 当前代码 checkpoint：`6375a72`。

---

## 0. 先定面试定位

不要把项目讲成“大型电商平台”。

统一口径：

> 一个电商 MVP + AI 客服项目，重点验证订单库存一致性和 Agent 受控调用业务能力。

面试时只讲三条主线：

```text
1. 登录 / JWT / RBAC
2. 下单 / 库存预占 / 取消释放
3. Agent 只读工具 + PREPARE 确认 / 管理员审批
```

RAG、Trace、售后换货只在被问到时展开，不主动铺开。

---

## 1. 当前项目状态

### 技术栈

```text
后端：Python 3.12 / FastAPI / Pydantic v2 / 异步 SQLAlchemy
数据库：MySQL 8 / Redis 7 / Qdrant
Agent：LangGraph / LangChain / DeepSeek
RAG：BGE-M3 / sentence-transformers / Qdrant
前端：React 18 / TypeScript / Vite / Ant Design / TanStack Query
测试：Pytest / Vitest / Playwright
工程：Alembic / Ruff / Mypy / Docker Compose
```

### 规模

```text
Backend app：103 个 Python 文件
Agent：33 个 Python 文件
Frontend：63 个 TS/TSX 文件
接口：约 70 个路由
业务表：14 张
测试：364 个
```

### 已完成

```text
全量中文注释
支付/退款遗留表和模型已删除
Agent 完整保留
数据库迁移到 80b9bbf33d5a
364 个测试通过
```

### 明确边界

```text
没有购物车
没有支付/退款
没有生产部署/HTTPS
Trace 是进程内缓冲，不持久化
Agent 模块参考现有架构，本人重点做业务接入和后端链路
```

被问到时如实说，不要夸大成“从零设计 Agent 平台”。

---

## 2. 三天速成计划

每天 3 小时，按顺序执行。

### Day 1：跑通 + 背介绍

**目标**

```text
项目能启动
Demo 能走通
30 秒 / 1 分钟介绍能脱稿
```

**任务**

1. 启动 Docker、后端、前端。
2. 准备三个浏览器标签页：
   - 普通用户
   - 管理员
   - 调试人员
3. 按第 7 节 Demo 脚本走一遍。
4. 背第 3 节介绍稿。
5. 读：

```text
README.md
docs/01-project-overview.md
docs/02-architecture.md
docs/03-business-flows.md
```

**产出**

一页纸画出：

```text
React -> FastAPI -> Service -> Repository -> MySQL
Agent -> LangGraph -> Tool -> Service
Redis：会话 / 锁 / 确认
Qdrant：向量召回
```

### Day 2：订单库存 + 登录权限

**目标**

```text
能讲清下单、取消、发货
能讲清 JWT、CurrentUser、CurrentAdmin
能回答 15 个基础追问
```

**阅读顺序**

```text
backend/app/models/order.py
backend/app/models/order_item.py
backend/app/models/inventory.py
backend/app/services/order.py
backend/app/services/inventory.py
backend/app/api/v1/orders.py
backend/app/core/token.py
backend/app/api/dependencies.py
```

**必须能画**

```text
CREATED -> CANCELLED
CREATED -> SHIPPED -> DELIVERED -> COMPLETED
```

**必须能说**

```text
下单：创建订单 + 订单项 + 预占库存，同一事务
取消：释放预占
发货：预占转实际扣减
防重复：idempotency_key + 唯一约束
防超卖：行锁 + 原子 UPDATE + WHERE 可用库存 >= 数量
```

### Day 3：Agent + Demo + 模拟面试

**目标**

```text
能用 2 分钟讲清 Agent 边界
Demo 连续跑 3 次不卡
录一遍模拟面试
```

**阅读顺序**

```text
agent/graph.py
agent/state.py
agent/context.py
agent/tools/registry.py
agent/tools/executor.py
agent/tools/confirmation.py
agent/approval_workflow.py
backend/app/services/agent_approval.py
```

**只背四句话**

```text
Agent 不直接访问数据库
LLM 不决定权限
READ Tool 只读
PREPARE 只生成待确认计划，执行走 Confirm 或管理员审批
```

**模拟面试**

让朋友随机问第 6 节的 10 个问题，录音回听。

---

## 3. 介绍稿

### 30 秒

> 这是一个电商 MVP 加 AI 客服项目。后端使用 FastAPI、MySQL、Redis，前端使用 React、TypeScript、Ant Design。用户端支持商品、下单、订单和售后；管理端支持发货、库存调整和审批。Agent 使用 LangGraph 做意图路由，只读工具查询商品和订单，高风险写操作走 PREPARE 加确认或管理员审批。我重点负责后端业务、权限和 Agent 接入，项目目前有 364 个测试。

### 1 分钟

> 后端是 FastAPI 加异步 SQLAlchemy，按 API、Service、Repository、Model 分层。订单创建时会在同一事务里写订单和订单项，并预占库存；取消释放预占，发货把预占转成实际扣减。幂等键和数据库唯一约束防止重复下单。
>
> Agent 侧用 LangGraph 做路由。工具分 READ 和 PREPARE：READ 只查数据，PREPARE 只生成待确认计划。用户确认或管理员审批后，才通过业务 Service 执行，Agent 不直接改数据库。
>
> 前端是 React 加 Ant Design，TanStack Query 管理服务端状态，Axios 统一处理 Token 和错误。

### 3 分钟展开顺序

```text
1. 项目目标和角色
2. 后端分层
3. 订单库存一致性
4. Agent 边界
5. 测试和边界
```

不要按接口列表讲。

---

## 4. 三条主线

### 主线 1：登录 / JWT / RBAC

流程：

```text
登录 -> 校验密码 -> 签发 Access Token
请求 -> Bearer Token -> 解析 claims -> 回查用户
CurrentUser / CurrentAdmin / CurrentDebugger
```

一句话答案：

```text
401 是没登录或 Token 无效；403 是登录了但权限不够。
```

```text
Token 还有效，但用户可能被禁用，所以每次请求回查数据库。
```

```text
前端路由守卫只改善体验，真正的权限在后端依赖里。
```

### 主线 2：订单 / 库存

流程：

```text
创建订单
-> 幂等键 + 参数指纹
-> 校验 SKU/商品/库存
-> 同一事务写订单、订单项
-> 预占库存
-> 返回 CREATED
```

取消：

```text
锁订单 -> 校验状态 -> 释放预占 -> CANCELLED
```

发货：

```text
锁订单 -> 扣减预占 -> SHIPPED
```

一句话答案：

```text
防重复下单：幂等键 + user_id/idempotency_key 唯一约束 + 冲突后回读。
```

```text
防超卖：行锁 + 原子 UPDATE + WHERE 可用库存 >= 数量，rowcount 为 0 就失败。
```

```text
订单项保存商品快照，商品改价改名不影响历史订单。
```

```text
事务边界在 Service，Repository 只 flush，不 commit。
```

### 主线 3：Agent 工具 / 审批

流程：

```text
用户问题
-> 意图路由
-> READ Tool 查询商品/订单
或
-> PREPARE Tool 生成 pending
-> 用户 Confirm
或
-> 管理员审批
-> 业务 Service 执行
```

一句话答案：

```text
Agent 不直接访问数据库，只通过受控 Tool 和 Service。
```

```text
LLM 输出不可信，库存调整是高风险写操作，所以只能 PREPARE。
```

```text
批准后还要重新校验库存，因为 Prepare 到 Approve 之间数据可能变化。
```

```text
用户身份来自后端 CurrentUser，不接受模型传入 user_id。
```

---

## 5. 代码讲解路线

面试时如果让你打开代码，只走这三条。

### 路线 A：登录

```text
backend/app/api/v1/auth.py
backend/app/services/auth.py
backend/app/core/token.py
backend/app/api/dependencies.py
```

讲解重点：

```text
Token 签发
密码 Argon2id
CurrentUser / CurrentAdmin
401 / 403
```

### 路线 B：下单

```text
backend/app/api/v1/orders.py
backend/app/services/order.py
backend/app/services/inventory.py
backend/app/repositories/inventory.py
```

讲解重点：

```text
create_order
idempotency_key
request_fingerprint
reserve / release / deduct_reserved
transaction_context
```

### 路线 C：Agent

```text
agent/graph.py
agent/tools/executor.py
agent/tools/confirmation.py
backend/app/services/agent_approval.py
```

讲解重点：

```text
意图路由
READ / PREPARE
pending_action
Confirm
管理员审批
```

---

## 6. 高频问题与一句话答案

### 后端基础

**1. 为什么用 FastAPI？**

```text
类型友好、Pydantic 校验、OpenAPI、异步生态、依赖注入。
```

**2. 为什么分层？**

```text
API 做协议转换，Service 管业务和事务，Repository 管 SQL，职责清晰。
```

**3. JWT 和 Session 区别？**

```text
JWT 无状态、适合前后端分离；Session 服务端存储、撤销更方便。
```

**4. 401 和 403？**

```text
401 身份未确认，403 身份已确认但没权限。
```

**5. 为什么密码用 Argon2id？**

```text
抗暴力破解和 GPU 加速，带随机盐，不存明文。
```

**6. 事务 ACID？**

```text
原子性、一致性、隔离性、持久性。
```

**7. 怎么防超卖？**

```text
行锁 + 原子 UPDATE + 条件判断，受影响行数为 0 就失败。
```

**8. 幂等键怎么设计？**

```text
客户端生成，服务端用 user_id + key 唯一约束，冲突时比较参数指纹。
```

**9. 索引怎么建？**

```text
高频 WHERE / JOIN / ORDER BY 列，区分度高，避免过多索引。
```

**10. N+1 怎么解决？**

```text
批量查询或 selectinload/join，避免循环里查关联表。
```

### 前端基础

**11. React Query 做什么？**

```text
服务端状态缓存、请求去重、loading/error、失效重取。
```

**12. Axios 拦截器做什么？**

```text
统一加 Token、处理 401、统一错误提示。
```

**13. 路由守卫怎么做？**

```text
根据当前用户角色决定可进入页面；后端仍要再校验。
```

**14. 前后端校验怎么分工？**

```text
前端改善体验，后端是最终边界。
```

### 项目问题

**15. 你负责什么？**

```text
后端业务、权限、订单库存、Agent 业务接入和审批链路。
```

**16. 最难的问题？**

```text
订单幂等和库存一致性：重复提交、并发扣减、取消释放、发货扣减。
```

**17. 如果重做？**

```text
先收敛功能面，统一订单号策略，补部署和监控，减少历史兼容代码。
```

**18. 怎么测试？**

```text
Pytest 覆盖订单、库存、权限和 Agent；测试库、Redis DB、Qdrant Collection 隔离。
```

**19. 为什么不用微服务？**

```text
单体事务边界清晰，当前规模不需要服务发现和分布式事务。
```

**20. 项目边界？**

```text
没有支付、购物车、生产部署；Trace 不持久化；Agent 模块参考现有架构。
```

---

## 7. 5 分钟 Demo

### 准备

```text
三个标签页：
A 普通用户
B 管理员
C 调试人员
```

当前 Token 存在 `sessionStorage`，每个标签页独立登录。

### 流程

```text
1. 普通用户登录
2. 商品列表 -> 商品详情
3. 立即购买 -> 创建订单
4. 我的订单 -> 取消
5. 管理员登录 -> 订单发货 -> 标记送达
6. 普通用户申请换货
7. 管理员审核
8. AI 导购：查询我的订单
9. Agent 提库存调整 -> 管理员审批
10. 可选：调试台看 Trace
```

### 讲解词

```text
这里是订单创建，库存被预占。
这里是取消，预占被释放。
这里是管理员发货，预占转为实际扣减。
这里是 Agent 只读工具。
这里是 PREPARE，只生成待确认计划。
这里是管理员审批后执行。
```

不要逐个页面介绍。

---

## 8. 简历写法

项目名：

```text
电商 MVP + AI 客服（FastAPI / React / MySQL / Redis / LangGraph）
```

三条 bullet：

```text
- 实现 JWT 登录、RBAC 和普通用户/管理员/调试人员三角色权限隔离。
- 实现订单创建、库存预占/释放/扣减，使用幂等键、唯一约束和事务保证一致性。
- 接入 LangGraph Agent，READ Tool 查询业务数据，PREPARE Tool 通过用户确认和管理员审批执行高风险操作。
```

测试：

```text
- 使用 Pytest 覆盖订单、库存、权限和 Agent 核心流程，项目共 364 个测试。
```

---

## 9. 不要说的话

```text
不要说：高并发
不要说：生产级
不要说：微服务
不要说：完整支付
不要说：所有代码都是我原创
不要说：70 个接口都是我设计的
```

如果被问 Agent：

```text
Agent 模块参考了现有架构，我主要做业务接入、Service 对接和审批链路调整。
```

如果被问不会的：

```text
这块我没有深入做，但我知道它的边界是……
```

诚实比硬编更加分。

---

## 10. 每天自检

### Day 1

- [ ] 项目能启动
- [ ] 三个角色能登录
- [ ] Demo 能走通
- [ ] 30 秒介绍能脱稿

### Day 2

- [ ] 能画订单状态机
- [ ] 能讲清预占/释放/扣减
- [ ] 能讲清幂等和防超卖
- [ ] 能回答 401/403、JWT、索引、N+1

### Day 3

- [ ] 能讲清 READ / PREPARE / Confirm
- [ ] 能讲清管理员审批
- [ ] Demo 连续 3 次不卡
- [ ] 录过一次模拟面试
- [ ] 简历项目描述改好

---

## 11. 怎么用这份文档问我

你可以按章节直接问，例如：

```text
第 4 节订单库存再讲细一点
第 6 节第 7 题防超卖，结合代码问我
模拟面试，按小公司初级全栈问我 10 个问题
这段介绍怎么改得更自然
面试官问 RAG 我怎么回答
```

推荐先看：

```text
第 3 节：介绍稿
第 4 节：三条主线
第 6 节：20 个问题
第 7 节：Demo
```

细节展开看：

```text
07-interview-qa.md
08-demo-script.md
09-study-plan.md
```
