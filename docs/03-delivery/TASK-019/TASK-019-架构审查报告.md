# TASK-019 架构审查报告

> 审查日期：2026-11-17  
> 审查范围：TASK-001～016 当前工作区真实源码  
> 审查性质：只读审查 + 设计建议  
> 代码/数据库/Docker 变更：无

## 1. 审查结论

当前 E-Commerce Agent 已经具备一条可运行、受控的 LangGraph 主链路，核心业务边界是正确的：

```text
Agent 不直接访问数据库
Tool 通过 Registry + Schema
Tool Handler 调用 Backend Service
写操作只暴露 Prepare Tool
Confirm 独立 API + Redis 一次性凭证
RAG 由 Backend 生成 Source
Output 校验 Secret 和 Source
```

但它还不是完整的“生产级三路编排 + HITL + Observability”架构。

### 总体判断

```text
现有架构：可运行、受控、可测试的 MVP/单图 Agent
目标架构：RAG / Tool / Workflow 三路 + Safety + Trace + HITL + Debug
建议：增量演进，不重写
```

## 2. 真实执行链路证据

### 入口

`backend/app/api/v1/agent.py::chat()`

```text
POST /agent/chat
  → CurrentUser
  → AgentRuntime(session, user, settings)
  → AgentRuntime.chat()
```

`ChatResponse` 当前字段：

```text
conversation_id
message_id
answer
sources
pending_action
created_at
```

没有 `trace_id`、`intent`、`route`、`token_usage`。

### Runtime

`agent/runtime.py::AgentRuntime.chat()`

```text
validate_user_message
→ RedisRateLimiter.check
→ ConversationStore.acquire_lock
→ AgentRuntimeContext
→ COMPILED_AGENT_GRAPH.ainvoke
→ release_lock
→ ChatResult
```

### 图

`agent/graph.py::build_agent_graph()`

真实节点：

```text
load_conversation
classify_intent
general_answer
retrieve_knowledge
knowledge_answer
unsupported_action
plan_tool
execute_tool
tool_answer
validate_output
save_conversation
```

真实 Intent：

```text
GENERAL
KNOWLEDGE
TOOL
UNSUPPORTED_ACTION
```

没有 `WORKFLOW`。

### Confirm

`backend/app/api/v1/agent.py::confirm_action()`

```text
ConfirmActionRequest
  → ConfirmationService.confirm()
  → ConfirmationStore.consume()
  → OrderService.cancel_order()
    或 AfterSaleService.apply()
```

确认不经过 LangGraph。

## 3. 当前架构的核心问题

### P0-1：没有统一 Trace

当前有：

- `request_id`（Runtime/State）；
- `agent_llm_completed` 日志（模型、Token、耗时）；
- `agent_execution_failed` 错误日志；
- `token_usage` State；
- conversation Redis。

缺少：

- trace_id 的对外/持久关联；
- 节点开始/结束/耗时；
- Tool 名称、参数摘要、风险、状态、耗时、错误码；
- intent/route 的结构化记录；
- Tool 调用与最终回答的关联；
- Debug 查询接口。

证据：

```text
agent/state.py 有 token_usage/tool_name/tool_args/tool_result
backend/app/schemas/agent.py 不返回 token/trace
agent/tools/executor.py 没有日志/耗时/trace
agent/nodes.py 没有节点事件记录
```

### P0-2：Prompt Injection 检测未接入主链路

`agent/guardrails.py` 定义了：

```text
looks_like_prompt_injection()
```

但当前没有在 `AgentRuntime.chat()`、`classify_intent_node()` 或路由中调用。

当前输入只做：

```text
Pydantic min/max
validate_user_message 的控制字符/空白/长度
```

不能把“函数存在”当成“输入注入检测已生效”。

### P1-1：三路边界不清晰

当前 `TOOL` 同时承载：

```text
只读查询
Prepare 操作
```

没有 `WORKFLOW` Intent。  
Prepare/Confirm 虽然实现了，但路由层没有把“查询”和“需要确认的工作流”分开。

### P1-2：RAG 没有无答案/低置信度边界

`KnowledgeRetrievalService.retrieve()`：

- 有 Qdrant + MySQL 权限过滤；
- 没有最低相关度阈值；
- 没有 no-answer 判定；
- `knowledge_answer_node` 只在 `select_context` 完全没有上下文时返回 `NO_KNOWLEDGE_ANSWER`。

TASK-015 的真实结果：

```text
No-answer Accuracy = 0
```

这是架构层问题，不是测试脚本问题。

### P1-3：HITL 与 Prepare/Confirm 未分层

当前：

```text
Prepare/Confirm
  = 用户确认当前一次操作
  = Redis PREPARED + nonce + TTL + 一次性消费

AfterSale
  = 业务状态 PENDING_REVIEW
  = 管理员 API approve/reject
```

真实存在的业务审批：

```text
AfterSaleService.approve()
AfterSaleService.reject()
AfterSale.reviewed_by / reviewed_at / review_note
```

但 Agent 没有：

- Workflow 实例；
- Approval Task；
- 审批通知；
- 恢复执行；
- 审计事件；
- LangGraph Checkpoint。

因此：

```text
已有售后业务审批
≠
已有 Agent HITL 工作流
```

### P2：目录和职责未表达

当前 `agent/` 扁平：

```text
graph.py
nodes.py
runtime.py
context.py
routing.py
guardrails.py
prompts.py
...
```

无法自然容纳：

```text
routing/
safety/
observability/
workflows/
evaluation/
```

## 4. 已有能力和缺失能力

### 已有

- Agent API 鉴权；
- Redis conversation / lock / rate limit；
- LangGraph 单图；
- Intent 规则 + LLM；
- RAG；
- Tool Registry/Schema/Executor；
- 10 个 Tool；
- Prepare/Confirm；
- Confirm 跨用户/nonce/过期/重复/参数 hash；
- Output Secret/Source 校验；
- RAG `trust=untrusted`；
- Backend Service 权限与事务；
- Agent 现有测试；
- 336 backend / 7 Playwright / 6 frontend 基线。

### 缺失

- 统一 trace；
- Tool risk 元数据实际使用；
- 输入 injection signal；
- 单 Tool 超时；
- RAG 低置信度/无答案；
- Workflow 路由；
- HITL Workflow/Approval/Audit；
- LangGraph Checkpoint；
- Debug API/Console；
- Agent 评测集成；
- 完整 PII 脱敏。

## 5. 建议优先级

### 第一优先级：Observability + Safety（不新增表）

```text
P1 Trace
P2 Safety
```

原因：

- 不改变业务规则；
- 不需要 migration；
- 立即提升可调试性；
- 为后续路由和评测提供数据；
- 风险低。

### 第二优先级：三路路由

```text
P3 RouteDecision
```

原因：

- 把查询、RAG、Workflow 的职责显式化；
- 保持 Prepare/Confirm 行为；
- 为 Debug Console 和 HITL 提供统一入口；
- 不需要新表。

### 第三优先级：RAG 无答案策略

需要独立评审，因为会改变：

- 召回结果；
- 回答“不知道”的行为；
- 评测指标；
- 用户体验。

不能在 TASK-019 中偷偷改检索阈值。

### 第四优先级：HITL 持久化

```text
P4_
```

需要：

- 新表；
- migration；
- 审批权限；
- 超时/并发/恢复；
- 审计；
- 独立验收。

不建议在 TASK-019 直接实施。

### 第五优先级：Debug Console + Evaluation

```text
P5 Debug Console
P6 Evaluation
```

依赖 P1/P3 的 Trace 和 Route。

## 6. 是否建议进入下一阶段实施

建议：**是，但只建议进入 P1～P3。**

建议顺序：

```text
1. Trace
2. Safety
3. 显式 RAG/TOOL/WORKFLOW 路由
4. 回归 + Debug 数据接口
5. 再评审 RAG 阈值
6. 再单独评审 HITL 数据模型
```

不建议立即做：

```text
- 新 Workflow 表
- migration
- Approval/Audit 表
- LangGraph Checkpoint 持久化
- 多 Agent / MQ / 微服务
```

## 7. 关键风险

| 风险 | 说明 | 建议 |
|---|---|---|
| Trace 泄露敏感数据 | Tool args/result 可能含 PII/Token | 白名单 + 脱敏 + TTL |
| Injection 误报 | 正常问题被拒绝 | signal + policy，不直接全量阻断 |
| 路由行为变化 | 模型/规则变化导致回答变化 | feature flag + 新旧路由回归 |
| RAG 阈值改变召回 | 可能降低可回答问题命中 | 独立配置、灰度、单独验收 |
| HITL 双写不一致 | Workflow 与 AfterSale 状态冲突 | 不复制业务状态；明确权威源 |
| Checkpoint 过期 | 长时间审批恢复失败 | 不让 Checkpoint 承担业务账本 |
| 过度设计 | 没有真实审批需求就建表 | P4 独立审批 |

## 8. 交付文档

- [TASK-019 Agent 现状架构分析](../../02-design/TASK-019-Agent-现状架构分析.md)
- [TASK-019 Agent 目标架构设计](../../02-design/TASK-019-Agent-目标架构设计.md)
- [TASK-019 Agent 重构实施计划](../../02-design/TASK-019-Agent-重构实施计划.md)
- [TASK-019 架构审查报告](TASK-019-架构审查报告.md)（本文）

## 9. 最终结论

```text
当前架构：可用，但观测性、三路边界、Safety 闭环、HITL 分层不足
建议：保留现有图和业务 Service，做增量重构
第一批：P1 Trace + P2 Safety
第二批：P3 三路路由
第三批：RAG 阈值评审
后续：HITL 数据模型（单独审批）
```

**本报告不把目标设计描述成已实现功能；未经明确批准，不开始代码重构。**
