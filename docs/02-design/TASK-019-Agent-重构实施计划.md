# TASK-019 Agent 重构实施计划

> 性质：实施计划，不是已完成的代码变更  
> 前置：TASK-019 现状分析和目标架构设计已评审  
> 约束：不推翻现有架构；不修改业务规则；不擅自新增 migration；Agent 不直接访问数据库

## 1. 实施原则

```text
先观测，后路由
先安全闭环，后 Workflow
先复用，后抽象
先无状态，后有状态
先低风险，后高审批成本
```

每个阶段必须满足：

- 保持现有 API 兼容；
- 保持现有 Backend Service 权限；
- 保持现有 Prepare/Confirm 行为；
- 不改变已通过的业务测试；
- 有独立回滚开关；
- 不把设计写成已实现。

## 2. 阶段总览

| 阶段 | 内容 | 风险 | 是否需要 migration | 建议 |
|---|---|---|---|---|
| P0 | 基线冻结和验收口径 | 低 | 否 | 立即 |
| P1 | Tool Trace / Observability | 低 | 否 | 第一批实施 |
| P2 | Safety Pipeline | 中 | 否 | 第一批实施 |
| P3 | RAG / Tool / Workflow 路由抽象 | 中 | 否 | 第二批 |
| P4 | Workflow/HITL 持久化 | 高 | **需要单独批准** | 第三批/后续 |
| P5 | Agent Debug Console | 中 | 否 | 与 P1/P3 配合 |
| P6 | Agent Evaluation | 低 | 否 | 持续 |

---

## 3. P0：基线冻结

### 目标

- 记录当前 Agent 行为和测试基线；
- 明确“改造前行为”与“改造后行为”；
- 建立 Trace/Debug 的验收标准。

### 文件

```text
docs/02-design/TASK-019-Agent-现状架构分析.md
docs/02-design/TASK-019-Agent-目标架构设计.md
docs/02-design/TASK-019-Agent-重构实施计划.md
docs/03-delivery/TASK-019/TASK-019-架构审查报告.md
```

### 测试

- 现有 336 backend tests；
- 现有 7 Playwright；
- 现有 6 frontend tests；
- 现有 Agent 测试：
  - `agent/tests/test_runtime.py`
  - `agent/tests/test_agent_tools.py`
  - `agent/tests/test_tools.py`
  - `agent/tests/test_context.py`
  - `agent/tests/test_conversation.py`

### 回滚

无代码变更，无需回滚。

---

## 4. P1：Tool Trace / Observability

### 目标

在不改变 Agent 行为的情况下，记录一次请求的：

- intent / route；
- 节点顺序和耗时；
- Tool 名称、参数摘要、风险、状态、耗时、错误；
- RAG 证据数量和 Top score；
- token usage；
- trace_id 与 conversation_id/user_id 的关联。

### 建议新增

```text
agent/observability/
├── __init__.py
├── events.py          # TraceEvent 数据结构
├── trace.py           # TraceCollector 抽象
├── redis_trace.py     # 短期 Redis Trace（TTL）
└── redaction.py       # 参数/结果脱敏
```

### 修改文件

```text
agent/context.py
  - 增加 trace_id / trace_collector（可选，默认 Noop）
agent/runtime.py
  - 创建 trace_id
  - 启动/结束 trace
  - 记录 runtime 阶段
  - 不改变 ChatResult 行为
agent/nodes.py
  - 在节点边界记录 node_start/node_end
  - 记录 intent/route/tool 摘要
  - 不改变节点返回值
agent/tools/executor.py
  - 记录 tool_start/tool_end/error
  - 记录 duration_ms
  - 对 args/result 脱敏
backend/app/api/v1/agent.py
  - 可选增加 debug 响应字段/接口
backend/app/schemas/agent.py
  - 可选增加 trace_id 和 DebugTraceResponse
frontend/src/types/agent.ts
frontend/src/api/agent.ts
frontend/src/pages/agent/AgentChat.tsx
  - 可选调试面板
```

### Trace 存储

第一阶段不新增数据库表：

```text
Redis key: agent:trace:{trace_id}
type: List 或 Stream
ttl: 与 conversation/debug 窗口一致
```

原因：

- 不修改 schema；
- 不新增 migration；
- 可快速验证 Trace 字段；
- 后续再评估 MySQL 审计表。

### 测试

新增：

```text
agent/tests/test_trace.py
  - trace_id 一次请求唯一
  - node events 顺序
  - tool event 正常/失败
  - duration_ms 非负
  - 脱敏字段不包含 JWT/Key/密码

agent/tests/test_trace_redaction.py
  - 订单地址/手机号/Token 不进入 Trace
  - 参数截断
  - 错误结果摘要脱敏
```

回归：

```text
agent/tests/test_runtime.py
agent/tests/test_agent_tools.py
backend tests
```

### 风险

| 风险 | 处理 |
|---|---|
| Trace 影响延迟 | 默认异步/Noop；Redis 写入失败不阻断主流程 |
| Trace 泄漏敏感数据 | 白名单 + 脱敏 + TTL |
| Trace 数据量过大 | 只存摘要和节点事件，不存 Prompt/完整结果 |
| Redis 不可用 | Trace 降级为日志，不阻断回答 |

### 回滚

- `trace_enabled` 开关；
- `TraceCollector` 默认 Noop；
- 关闭开关后行为与当前一致；
- 不需要回滚数据（Redis TTL）。

---

## 5. P2：Safety Pipeline

### 目标

把现有分散的 Guardrails 收拢为显式安全管道，不重复实现 Backend 权限。

### 当前已有

- `validate_user_message`；
- `looks_like_prompt_injection`（未接入）；
- `validate_output`；
- Source 校验；
- Secret 模式；
- `trust=untrusted` RAG context；
- Tool Registry/Schema；
- Redis Confirm；
- Backend Service 权限。

### 建议新增

```text
agent/safety/
├── __init__.py
├── input.py            # normalize/validate/injection signal
├── policy.py           # 安全策略/feature flags
├── output.py           # secret/length/source/PII
└── redaction.py        # 统一脱敏
```

### 接入点

```text
AgentRuntime.chat
  → SafetyInput.normalize()
  → SafetyInput.injection_signal()
  → 记录 safety event
  → 继续现有图
```

注意：

- Injection signal **不直接替代权限**；
- 可疑输入不必然拒绝，可进入安全回答/降级路径；
- 不能因为增加 Safety 就重复实现 `CurrentUser`、Order ownership、AfterSale ownership；
- 输出 Secret/Source 检查继续保留。

### 修改文件

```text
agent/guardrails.py
  - 保留现有函数，逐步迁移到 safety/
agent/runtime.py
  - 接入 input safety
agent/nodes.py
  - 输出安全仍走 validate_output_node
agent/prompts.py
  - 明确“untrusted”边界；不新增权限承诺
```

### 测试

```text
agent/tests/security/test_task015_security.py
  - 现有 Prompt Injection/Secret/Source 测试
新增:
  - injection signal 被记录
  - 可疑输入不越权调用 Tool
  - 输出 PII/Token 脱敏
  - 误报不会导致正常知识/查询全部失败
```

### 风险

- 误报导致正常请求被拒绝：使用 signal + policy，不直接全量阻断；
- 安全检查重复：只做 Agent 层输入/输出，不重做 Backend ACL；
- PII 误判：规则 + 白名单，不依赖 LLM。

### 回滚

- `safety_injection_enabled` 开关；
- 保留旧 `validate_user_message` 路径；
- 关闭后行为与当前一致。

---

## 6. P3：RAG / Tool / Workflow 路由抽象

### 目标

把当前四 Intent 重构为显式 RouteDecision，同时保持现有 API 兼容：

```text
GENERAL
RAG        （兼容 KNOWLEDGE）
TOOL       （只读业务查询）
WORKFLOW   （Prepare/Confirm/HITL）
UNSUPPORTED
```

### 当前行为

- `KNOWLEDGE` → RAG；
- `TOOL` → 查询 + Prepare；
- 没有 WORKFLOW。

### 目标行为

- 查询 Tool 走 TOOL；
- `prepare_cancel_order` / `prepare_create_after_sales` 走 WORKFLOW；
- Confirm 仍是独立 API，不塞回图；
- HITL 只做接口预留，不在本阶段实现。

### 建议新增

```text
agent/routing/
├── __init__.py
├── intent.py
├── rules.py
└── decisions.py
```

`decisions.py`：

```text
RouteDecision(route, reason, confidence, risk_level, source)
```

### 修改文件

```text
agent/routing.py
  - 保留函数兼容，内部改为 RouteDecision
agent/graph.py
  - 新增 workflow 路由入口；保留旧 knowledge/tool 节点兼容
agent/nodes.py
  - 拆出 route/workflow 节点，避免节点继续膨胀
agent/state.py
  - 增加 route / risk_level / trace_id（可选）
```

### 关键约束

- 不在本阶段新增 Workflow 表；
- 不改变 Confirm API；
- 不改变 Prepare Tool 行为；
- 不改变 Backend Service；
- 旧 `KNOWLEDGE` 标签可映射为 RAG，避免 API 破坏。

### 测试

- 所有现有 `agent/tests`；
- 新增路由测试：
  - “查询订单” → TOOL；
  - “退货政策” → RAG；
  - “取消订单” → WORKFLOW；
  - “申请退款” → UNSUPPORTED；
  - 模型返回未知标签 → 安全回退；
  - 规则优先于 LLM 的写操作边界。

### 风险

- 现有模型不遵循新的 Route 标签；
- 路由改动导致旧回答变化；
- Prepare 从 TOOL 迁到 WORKFLOW 后前端行为变化。

### 回滚

- `routing_v2_enabled` 开关；
- 回退到旧 `route_intent`；
- 新老路由共用现有节点；
- 不涉及数据迁移。

---

## 7. P4：Workflow/HITL 持久化

> 本阶段涉及数据库结构，必须单独审批，不属于 TASK-019 默认实施范围。

### 目标

把“用户确认”和“人工审批”分离：

```text
Prepare/Confirm：Redis + 用户确认 + Backend 执行
HITL：MySQL Workflow + Approval + Audit + 管理员审批
```

### 建议表（需单独评审）

```text
agent_workflow_instances
  id, workflow_no, user_id, type, status,
  business_resource_type, business_resource_no,
  current_step, created_at, updated_at, completed_at

agent_workflow_events
  id, workflow_id, event_type, actor_type, actor_id,
  from_status, to_status, payload_json, created_at

agent_approval_tasks
  id, workflow_id, status, assignee_id,
  decision, decision_note, expires_at,
  decided_at, created_at, updated_at

agent_audit_events
  id, trace_id, actor_type, actor_id,
  event_type, resource_type, resource_no,
  metadata_json, created_at
```

### 与现有 AfterSale 的关系

- 继续使用现有 `after_sales` 业务表；
- `AfterSale.status` 是业务状态；
- Workflow 表记录流程实例和审批；
- 不把业务状态复制成第二套权威状态；
- 通过 `business_resource_no` 关联，不破坏现有 Service。

### LangGraph Checkpoint

可选方案：

- Redis Checkpoint：短 TTL，图执行恢复；
- MySQL Checkpoint：更长生命周期，但需要额外表/依赖；
- 不建议为了 HITL 马上引入新的存储组件。

原则：

```text
LangGraph Checkpoint 保存图位置
MySQL Workflow 保存业务生命周期
Approval 保存人工决策
Audit 保存事件
```

### 必须处理的场景

- 重复审批；
- 审批超时；
- 并发审批；
- 审批后 Service 失败；
- 用户取消申请；
- 审批人与申请人相同（权限策略）；
- 跨用户/跨管理员访问；
- 幂等键；
- 流程恢复。

### 测试

需要独立的 HITL 测试套件：

```text
workflow creation
approve
reject
timeout
concurrent approve
duplicate approve
resume after failure
audit immutability
```

### 风险

- 数据模型设计错误，后续迁移成本高；
- 双写不一致（Workflow vs AfterSale）；
- 审批权限绕过；
- 长时间暂停导致状态过期；
- 没有真实业务审批需求时过度设计。

### 回滚

- 本阶段必须独立发布；
- 数据表先只增不改；
- 通过 feature flag 关闭 Agent HITL；
- 保留现有 AfterSale API；
- 不删除业务数据。

---

## 8. P5：Agent Debug Console

### 目标

在现有 `AgentChat.tsx` 基础上增加管理员调试视图。

### 新增/修改

```text
backend/app/api/v1/agent.py
  - GET /agent/runs/{trace_id}（管理员）
backend/app/schemas/agent.py
  - DebugTraceResponse
frontend/src/pages/agent/AgentChat.tsx
  - Trace 抽屉/时间线
frontend/src/pages/agent/DebugTrace.tsx
frontend/src/types/agent.ts
frontend/src/api/agent.ts
```

### 展示字段

```text
trace_id
intent/route
node timeline
tool name + args summary + risk
tool status + duration + error
RAG sources + scores
final answer
pending action
```

### 安全

- 仅管理员；
- 脱敏；
- 不展示 System Prompt；
- 不展示完整 Tool 原始结果；
- 不展示其他用户信息；
- Trace TTL；
- Debug API 不替代审计。

### 测试

- 普通用户 403；
- 管理员可查；
- 无 Trace 404；
- 脱敏字段不存在；
- 前端不展示敏感字段。

---

## 9. P6：Agent Evaluation

### 目标

把现有 TASK-015 的 Agent 抽样扩展为可重复评测。

### 新增

```text
agent/evaluation/
├── cases.py
├── runner.py
├── metrics.py
└── report.py
```

指标：

```text
Intent Accuracy
Route Accuracy
Tool Selection Accuracy
Argument Accuracy
Execution Success
Grounded Answer
Unsupported Claim Rate
Refusal Accuracy
```

### 约束

- Fake LLM 与真实 DeepSeek 分开；
- 不把 Fake 通过率当真实准确率；
- 记录模型、Prompt 版本、数据集版本、耗时、Token；
- 不记录密钥；
- 复用 TASK-015 数据集，不覆盖旧结果。

---

## 10. 必要工作与后续增强

### 必要（建议先做）

1. Trace；
2. Safety 接入；
3. 显式三路 Route；
4. RAG 无答案/低置信度策略评审；
5. Debug 查询接口；
6. 回归测试。

### 后续增强

1. HITL Workflow 表；
2. Approval/Audit；
3. LangGraph Checkpoint；
4. 独立 Debug Console 页面；
5. 全量真实模型评测；
6. 更细粒度 Tool 超时/熔断。

## 11. 文件级变更预估

### P1

```text
新增:
  agent/observability/*
  agent/tests/test_trace*.py
修改:
  agent/context.py
  agent/runtime.py
  agent/nodes.py
  agent/tools/executor.py
  backend/app/schemas/agent.py
  backend/app/api/v1/agent.py
  frontend/src/types/agent.ts
  frontend/src/api/agent.ts
  frontend/src/pages/agent/AgentChat.tsx
```

### P2

```text
新增:
  agent/safety/*
修改:
  agent/runtime.py
  agent/guardrails.py
  agent/tests/security/*
```

### P3

```text
新增:
  agent/routing/*
修改:
  agent/routing.py
  agent/graph.py
  agent/nodes.py
  agent/state.py
```

### P4（需审批）

```text
新增:
  alembic/versions/*_agent_workflow_tables.py
  agent/workflows/hitl.py
  agent/workflows/store.py
  backend/app/models/agent_workflow*.py
  backend/app/services/agent_workflow.py
  backend/app/api/v1/admin/agent_approvals.py
```

### P5/P6

```text
新增:
  frontend/src/pages/agent/DebugTrace.tsx
  agent/evaluation/*
  docs/04-testing/TASK-019/*
```

## 12. 每阶段验收门

### P1

- 336+ tests 全绿；
- Trace 不影响响应；
- 无 Secret/PII；
- 可以按 trace_id 关联一次请求。

### P2

- 现有安全测试全绿；
- Injection 只作为 signal，不误杀正常查询；
- 输出脱敏；
- Backend 权限不变。

### P3

- 现有 Agent 行为保持；
- RAG/TOOL/WORKFLOW 路由可测；
- Prepare/Confirm 行为不变；
- 所有 Tool 仍有权限边界。

### P4

- 必须单独审批；
- migration 可回滚；
- 审批/审计/业务状态不双写冲突；
- 并发/超时/重复审批测试通过。

### P5/P6

- Debug 仅管理员；
- 评测结果可重复；
- 不泄露密钥。

## 13. 风险与回滚

| 风险 | 等级 | 回滚 |
|---|---|---|
| Trace 增加延迟 | 中 | Noop/异步/开关 |
| Trace 泄露敏感信息 | 高 | 白名单、脱敏、TTL |
| Injection 误报 | 中 | signal-only、策略开关 |
| 路由改变回答 | 高 | `routing_v2_enabled`，保留旧路由 |
| RAG 阈值改变召回 | 高 | 独立配置、灰度/关闭 |
| Workflow 双写不一致 | 高 | 不改业务表；Workflow 只读投影；事务/补偿 |
| Checkpoint 过期 | 中 | 不把 Checkpoint 当业务账本 |
| 审批越权 | 高 | Backend CurrentAdmin + 审批表权限 |
| 需求过度设计 | 中 | P4 单独审批，不默认实施 |

## 14. 结论

建议先实施：

```text
P1 Trace
P2 Safety
P3 三路路由
```

暂不实施：

```text
P4 HITL 数据表 / migration
```

原因：

- P1～P3 不改变业务规则，不需要 migration；
- P4 涉及新表、审批权限和长期状态，必须先评审业务需求和 schema；
- 当前 `AfterSale` 已有审批 API，但没有通用 Workflow/Audit，不能把“已有售后审批”直接等同于 Agent HITL。

**未经明确批准，不开始 P1 代码修改。**
