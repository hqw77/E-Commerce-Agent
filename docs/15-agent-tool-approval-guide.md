# 15 Agent 工具与审批完整教程

这篇只讲 Agent 的工具和审批主线：

```text
用户问题
-> 意图识别
-> LangGraph 路由
-> READ 工具 或 PREPARE 工具
-> 用户确认 / 管理员审批
-> 业务 Service 执行
```

当前项目里：

READ 工具只读。

PREPARE 工具只生成待确认或待审批计划。

真正执行一定走业务 Service。

Agent 不直接访问数据库。

---

# 第一部分：先把概念讲明白

## 1. Agent 在这个项目里做什么

不是让大模型直接操作数据库。

而是让大模型：

```text
理解用户想做什么
选择受控工具
读取业务数据
生成待确认计划
```

真正的业务规则、权限、事务和状态机仍然在后端 Service。

## 2. READ 工具

READ 只查询，不改变业务状态。

例如：

```text
查商品
查 SKU
查库存
查我的订单
查我的售后
```

READ 工具可以返回结构化数据，模型再总结给用户。

## 3. PREPARE 工具

PREPARE 不直接执行写操作。

它只生成一个计划：

```text
取消订单
申请售后
库存调整
```

PREPARE 返回一个 pending_action。

前端看到 pending_action 后，显示待确认或待审批。

## 4. 用户确认和管理员审批的区别

用户确认：

```text
消费者自己发起的低风险动作
例如取消自己的订单、申请售后
确认后由 Confirm API 执行
```

管理员审批：

```text
高风险动作
例如库存调整
由管理员在审批中心批准或拒绝
```

两条路径不能混用。

## 5. 为什么 Agent 不能直接改数据库

因为模型输出不可信。

模型可能：

```text
理解错用户意图
生成错误参数
重复调用工具
被 Prompt 注入影响
```

所以：

```text
LLM 只负责规划和选择工具
Tool 只负责调用 Service
Service 才负责业务规则和事务
```

---

# 第二部分：项目里怎么写的

## 1. 核心文件

主图：

agent/graph.py

意图和路由：

agent/routing.py

Tool 白名单：

agent/tools/registry.py

Tool 执行器：

agent/tools/executor.py

用户确认：

agent/tools/confirmation.py

库存审批子图：

agent/approval_workflow.py

审批业务：

backend/app/services/agent_approval.py

Tool 定义：

agent/tools/product.py

agent/tools/order.py

agent/tools/inventory.py

## 2. Tool 有哪些

READ：

```text
search_products
get_product_detail
get_sku_detail
check_sku_inventory
list_my_orders
get_my_order
list_my_after_sales
get_my_after_sales
```

PREPARE：

```text
prepare_cancel_order
prepare_create_after_sales
prepare_adjust_inventory
```

## 3. 主图怎么走

graph.py 里的流程：

```text
START
-> load_conversation
-> classify_intent
-> router
-> general_answer / retrieve_knowledge / plan_tool / plan_workflow / unsupported_action
-> execute_tool
-> tool_answer
-> validate_output
-> save_conversation
-> END
```

只需要记住：

```text
router 决定走 READ、RAG、Workflow 还是普通回答
plan_tool 只暴露 READ 工具
plan_workflow 只暴露 PREPARE 工具
execute_tool 才真正执行工具
```

## 4. 意图识别怎么走

routing.py 的顺序：

```text
先跑确定性正则
-> 命中就直接返回
-> 没命中才调用 LLM
-> LLM 返回的标签必须通过白名单解析
```

确定性规则优先，减少 Token，也防止模型把明确的写操作误判成只读。

---

# 第三部分：三条完整链路

## 链路 1：READ 查询

例子：

```text
用户问“查一下我的订单”
```

流程：

```text
前端 /agent/chat
-> AgentRuntime
-> graph
-> classify_intent
-> router
-> plan_tool
-> 只暴露 READ 工具
-> LLM 选择一个工具
-> ToolExecutor 校验工具名和参数
-> handler 调 OrderService
-> OrderService 按当前用户查订单
-> ToolResult
-> tool_answer
-> 返回给用户
```

关键点：

```text
ToolContext 里的 user 来自后端 CurrentUser
模型不能传 user_id
工具名必须在 Registry 白名单
参数必须通过 Pydantic
```

## 链路 2：PREPARE + 用户确认

例子：

```text
用户说“取消订单”
```

流程：

```text
router 识别 WORKFLOW
-> plan_workflow
-> 只暴露 PREPARE 工具
-> LLM 选择 prepare_cancel_order
-> handler 校验订单归属和状态
-> ConfirmationStore.create
-> 写入 Redis pending
-> 返回 pending_action
-> 前端显示确认卡片
-> 用户点确认
-> POST /agent/actions/{id}/confirm
-> ConfirmationService.confirm
-> ConfirmationStore.consume
-> 调 OrderService.cancel_order
-> 返回执行结果
```

Redis 记录里包含：

```text
confirmation_id
user_id
conversation_id
operation
resource_no
arguments
params_hash
nonce
expires_at
```

Confirm 时用 Lua 原子校验：

```text
记录存在
状态是 PREPARED
user_id 匹配
conversation_id 匹配
nonce 匹配
未过期
```

全部通过后删除记录并返回内容。

同一记录只能消费一次，防止重复执行。

## 链路 3：PREPARE + 管理员审批

例子：

```text
库存调整
```

流程：

```text
Agent 选择 prepare_adjust_inventory
-> AgentApprovalService.create_inventory_adjustment
-> 校验管理员权限
-> 读取当前库存
-> 计算 before 和 planned
-> 写 MySQL agent_approvals
-> 写 Redis pending
-> start_approval 启动审批子图
-> 审批子图 interrupt 等待管理员
-> 管理员在审批中心批准
-> AgentApprovalService.approve
-> 行锁确认仍是 pending
-> 先写 approved
-> resume_approval 恢复子图
-> 重新读取库存
-> 对比 before_data
-> 调 InventoryService.adjust
-> 记录 executed
-> 清理 Redis
```

如果库存已经变化：

```text
标记 failed
返回 AGENT_APPROVAL_STALE
不覆盖当前库存
```

这就是为什么批准后还要重新校验，不能相信 PREPARE 时的快照。

## 前端链路

消费者发起 Agent 对话：

```text
frontend/src/pages/agent/AgentChat.tsx
-> frontend/src/api/agent.ts 的 chat
-> POST /agent/chat
-> 响应里的 pending_action
-> PendingActionCard 显示确认信息
```

用户确认：

```text
PendingActionCard
-> api/agent.ts 的 confirmAction
-> POST /agent/actions/{confirmation_id}/confirm
-> ConfirmationService.confirm
```

管理员审批：

```text
frontend/src/pages/agent/AgentApprovals.tsx
-> frontend/src/api/agentApprovals.ts
-> 审批列表 / 详情 / approve / reject
-> AgentApprovalService
```

前端只负责展示 pending 和发起确认/审批请求。

真正执行和权限校验仍在后端。

---

# 第四部分：代码阅读顺序

不要从 agent 包第一行读到尾。

按下面顺序读。

## 第 1 步：主图装配

打开 agent/graph.py。

只看：

```text
START -> load_conversation -> classify_intent -> router
```

以及 router 的条件边：

```text
general_answer
retrieve_knowledge
plan_tool
plan_workflow
unsupported_action
```

不用先看每个 node 的内部实现。

## 第 2 步：意图和路由

打开 agent/routing.py。

只看：

```text
obvious_unsupported_action
obvious_workflow_action
obvious_tool_action
classify_intent
node_for_route
```

要能说出：

```text
规则优先
LLM 兜底
模型标签必须经过白名单
```

## 第 3 步：工具白名单

打开 agent/tools/registry.py。

只看：

```text
register
get
openai_tools
```

要能说出：

```text
同名工具不能重复注册
模型只能调用已注册工具
READ 和 PREPARE 分开
```

## 第 4 步：工具执行

打开 agent/tools/executor.py。

只看 execute：

```text
限制调用次数
校验工具名
校验参数
调用 handler
转换错误
记录 Trace
```

要能说出：

```text
Executor 不访问数据库
handler 才调用 Service
业务异常转成 ToolResult
未知异常转成 AgentToolExecutionError
```

## 第 5 步：用户确认

打开 agent/tools/confirmation.py。

只看：

```text
ConfirmationStore.create
ConfirmationStore.consume
ConfirmationService.confirm
```

重点：

```text
Redis 只存短期 pending
Lua 原子消费
nonce、user、conversation、参数 hash 都要匹配
Confirm 后才调用 Service
```

## 第 6 步：管理员审批

打开 backend/app/services/agent_approval.py。

只看：

```text
create_inventory_adjustment
approve
reject
```

重点：

```text
MySQL 是审批状态权威源
Redis 是短期 pending
审批子图只负责等待
真正业务执行在 approve 里
批准后重新校验库存
```

## 第 7 步：审批子图

打开 agent/approval_workflow.py。

只看：

```text
wait_for_admin
start_approval
resume_approval
```

只要知道：

```text
interrupt 暂停
Command(resume=...) 恢复
InMemorySaver 保存暂停状态
进程重启可以重建中断
```

## 第 8 步：Tool handler

打开：

```text
agent/tools/product.py
agent/tools/order.py
agent/tools/inventory.py
```

只看一个 READ 和一个 PREPARE。

例如：

```text
get_my_order
prepare_cancel_order
prepare_adjust_inventory
```

要能说出：

```text
handler 只做参数校验和 Service 调用
真正的业务规则在 Service
```

---

# 第五部分：代码怎么读才不容易忘

## 方法一：三遍法

第一遍只看成功路径。

```text
READ 查询成功
PREPARE 生成 pending
用户确认成功
管理员审批成功
```

第二遍只看失败路径。

```text
工具不存在
参数不合法
调用次数超限
用户确认 nonce 不匹配
确认记录过期
审批记录不是 pending
库存已变化
审批恢复失败
```

第三遍看测试。

重点看：

```text
agent/tests/test_agent_tools.py
backend/tests/api/test_agent.py
backend/tests/test_agent_approval.py
```

测试会告诉你每个边界的期望结果。

## 方法二：跟一次 READ

打开 Agent 对话，问：

```text
查一下我的订单
```

在 plan_tool 打断点，看模型选了哪个工具。

在 executor 打断点，看 raw_args 和校验后的 args。

在 OrderService 打断点，看 user_id 和订单号。

## 方法三：跟一次 Confirm

让 Agent 准备取消订单。

在 ConfirmationStore.consume 打断点，看 Lua 返回值。

在 ConfirmationService.confirm 打断点，看 record 和 operation。

在 OrderService.cancel_order 打断点，看状态和库存释放。

## 方法四：合上代码画图

画两条线：

```text
READ：问题 -> 工具 -> Service -> 回答
PREPARE：问题 -> 工具 -> pending -> 确认/审批 -> Service
```

画不出来，就回到对应节点重读。

---

# 第六部分：面试怎么讲

## 30 秒版

这个项目的 Agent 不直接访问数据库，而是通过受控工具调用业务 Service。

工具分 READ 和 PREPARE。READ 只查询商品、订单、库存；PREPARE 只生成待确认或待审批计划。用户确认后走 Confirm，管理员审批后走 AgentApprovalService，真正执行仍然走业务 Service。

这样既让 Agent 能调用真实业务，又不会让模型直接改库或绕过权限。

## 1 分钟版

Agent 主图用 LangGraph 编排，先加载会话、识别意图，再路由到普通回答、RAG、READ 工具或 PREPARE 工作流。

READ 工具只读，工具名必须在 Registry 白名单里，参数必须通过 Pydantic 校验，handler 再调用 OrderService、ProductService 这些业务 Service。

PREPARE 工具不直接执行写操作。取消订单和售后申请写 Redis pending，返回待确认卡片，用户确认后由 Confirm API 消费 pending 并调用 Service。库存调整是高风险操作，写 MySQL 审批记录和 Redis pending，由管理员在审批中心批准，批准后重新读取库存，确认没有变化才调用 InventoryService.adjust。

Agent 不直接访问数据库，LLM 不决定权限，工具调用和业务执行是分开的。

---

# 第七部分：高频面试题

## 1. Agent 为什么不能直接访问数据库

模型输出不可信，可能理解错、参数错、重复调用或被注入。

所以模型只能选择受控工具，工具再调用业务 Service。

## 2. READ 和 PREPARE 的区别

READ 只查询，不改变状态。

PREPARE 只生成待确认或待审批计划，不直接执行。

## 3. 用户确认和管理员审批的区别

用户确认用于消费者自己的低风险动作，例如取消订单、申请售后。

管理员审批用于高风险动作，例如库存调整。

两条路径独立，不能混用。

## 4. 工具名和参数怎么校验

工具名必须在 Registry 白名单。

参数必须通过 Pydantic Schema。

未知工具直接拒绝。

## 5. Confirm 怎么防止重复执行

Redis Lua 原子校验并删除记录。

同一条确认记录只能消费一次。

user_id、conversation_id、nonce、参数 hash 都要匹配。

## 6. 确认记录过期怎么办

Redis 记录带 TTL。

过期后 Confirm 返回确认已过期。

用户需要重新让 Agent 生成计划。

## 7. 为什么 PREPARE 不直接执行

因为 LLM 可能误解用户意图。

PREPARE 只记录计划，用户或管理员确认后才执行。

## 8. 为什么批准后还要重新校验库存

PREPARE 到批准之间，库存可能被其他订单改变。

不能相信旧快照。

如果总量变化，标记 stale，不执行。

## 9. 审批状态存在哪里

MySQL 是权威源。

Redis 只存短期 pending。

审批子图只负责暂停和恢复，不保存业务正文。

## 10. 进程重启后审批还能恢复吗

MySQL 审批记录还在。

审批子图使用 InMemorySaver，内存线程会丢失。

resume_approval 检测到线程丢失时会重建中断，再恢复。

## 11. 为什么工具调用要限制次数

防止模型循环调用、重复调用或无限重试。

Executor 每轮有 max_calls。

## 12. 工具执行失败怎么处理

业务异常转成 ToolResult(ok=False)，把错误码返回给模型总结。

未知异常转成 AgentToolExecutionError。

## 13. Agent 怎么保证用户隔离

ToolContext 的 user 来自后端 CurrentUser。

模型不能传 user_id。

Service 再按 user_id 校验资源归属。

## 14. Agent 和 RAG 的关系

RAG 只负责知识问答。

工具负责真实业务数据。

两条路径都由主图路由，但互不替代。

## 15. 这个 Agent 方案有什么边界

当前是本地演示项目。

审批子图使用 InMemorySaver。

Agent 模块参考了已有架构，重点在业务接入和审批链路。

---

# 第八部分：最容易答错的点

错误一：说 Agent 直接查数据库。

正确：Agent 通过 Tool 调 Service，Service 再访问数据库。

错误二：说 PREPARE 会直接执行。

正确：PREPARE 只生成 pending。

错误三：说用户确认和管理员审批是一回事。

正确：用户确认走 ConfirmationService，管理员审批走 AgentApprovalService。

错误四：说批准后直接按旧库存执行。

正确：批准后要重新读取库存，变化则标记 stale。

错误五：说 Redis 是审批状态的权威源。

正确：MySQL 是权威源，Redis 只存短期 pending。

错误六：说前端确认按钮就是权限控制。

正确：Confirm 仍要校验 user、conversation、nonce 和参数 hash。

---

# 第九部分：五分钟自检

1. Agent 为什么不能直接访问数据库？

2. READ 和 PREPARE 的区别？

3. 用户确认和管理员审批分别用在哪里？

4. Confirm 怎么防止重复执行？

5. 确认记录过期怎么办？

6. 批准后为什么还要重新校验库存？

7. 审批状态存在哪里？

8. 进程重启后审批怎么恢复？

9. 工具名和参数怎么校验？

10. Tool 执行失败怎么返回？

---

# 第十部分：最后背这一句

Agent 用 LangGraph 做路由，READ 工具只查数据，PREPARE 只生成待确认或待审批计划；用户确认走 Confirm，管理员审批走 AgentApprovalService，真正执行仍然走业务 Service，Agent 不直接改数据库，LLM 也不决定权限。
