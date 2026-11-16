# TASK-015 最终验收报告

> 日期：2026-11-17  
> 分支：`feature/task-004-order`  
> 状态：自动化实施完成，存在明确未验证/未通过项  
> 真实支付宝沙箱：SKIPPED_CREDENTIALS

## 1. 阶段结论

| Phase | 内容 | 结果 |
|---|---|---|
| 015.1 | 测试方案与数据准备 | 完成 |
| 015.2 | Backend E2E | 复用现有 integration，全量通过 |
| 015.3 | 支付 Mock/本地签名/Fake HTTP | 通过；真实沙箱跳过 |
| 015.4 | 安全测试 | 新增 5 个测试通过，复用已有越权/Confirm 测试 |
| 015.5 | RAG 评估 | 执行完成；No-answer Accuracy 0 |
| 015.6 | Agent 评估 | 30 条数据集；真实 DeepSeek 10/10 抽样通过 |
| 015.7 | 回归与报告 | 完成 |

不能把本报告理解为“全部 AI 指标通过”或“真实支付沙箱通过”。

---

## 2. 测试结果

### 全量自动化

```text
pytest:        336 passed
Playwright:    7 passed
Frontend:      6 passed
typecheck:     passed
lint:          passed
build:         passed
Ruff:          passed
Mypy:          128 source files, no issues
Alembic check: no new operations
```

新增 5 个测试：

```text
agent/tests/security/test_task015_security.py          3
backend/tests/security/test_task015_payment_security.py 2
```

### Playwright

```text
7 passed (21.0s)
```

新增/加强断言：

- 分类创建（实际提交、列表出现新分类）；
- 知识库上传新版本（真实文件上传、版本处理）；
- 原有分类编辑、商品、库存、订单、售后、认证、Agent Prepare/Confirm、RAG 发布/检索。

### Docker

```text
app       Up
mysql     Up healthy
redis     Up healthy
qdrant    Up
```

```text
/api/v1/health/live   200
/api/v1/health/ready  200
```

---

## 3. 支付结果

```text
MOCK_VERIFIED
LOCAL_SIGN_VERIFIED
FAKE_HTTP_VERIFIED
REAL_SANDBOX: SKIPPED_CREDENTIALS
```

当前缺少：

```text
ALIPAY_APP_ID
ALIPAY_PRIVATE_KEY
ALIPAY_PUBLIC_KEY
ALIPAY_NOTIFY_URL
```

现有测试覆盖 Mock 支付、支付状态、库存、退款、Fake 退款查询和幂等；新增本地签名/身份/篡改测试。真实沙箱支付、异步通知、退款、退款查询未执行。

---

## 4. 安全结果

新增测试覆盖：

- Prompt Injection 模式识别；
- System Prompt/Key 形式输出拒绝；
- 伪造 RAG Source 拒绝；
- 支付签名、金额篡改、app_id/seller_id 不匹配；
- 未配置支付宝明确失败。

复用已有测试覆盖：

- 认证、Refresh Rotation、重放、并发；
- 普通用户 403；
- 跨用户订单/Agent 会话隔离；
- Tool Registry、Schema、`user_id` 禁止；
- Prepare/Confirm 跨用户、nonce、过期、重复、并发、参数篡改；
- 知识库 ACL。

真实 DeepSeek 抽样中，Prompt Injection 和指定其他用户用例没有产生 Pending 或跨用户结果。

限制：

- Chat API 不返回完整 Tool Call 轨迹；
- 真实模型拒绝行为不能替代后端权限；
- 未做浏览器 XSS 扫描。

---

## 5. RAG 评估结果

数据集：

```text
version: task015-rag-v1
documents: 5
questions: 33
answerable: 25
no_answer: 8
```

结果：

```text
Recall@5:              1.0000
Precision@5:           0.2000
MRR:                   1.0000
Empty Retrieval Rate:  0.0000
No-answer Accuracy:    0.0000
Chunk Keyword Hit:     1.0000
```

真实发现：

- 25 个可回答问题全部命中预期文档；
- 8 个无答案问题全部返回了相似文档；
- 当前 Retrieval 没有无答案阈值，`No-answer Accuracy=0`；
- Chunk 指标是关键词覆盖，不是精确 Chunk Recall；
- ACL 评估未纳入本数据集。

这是 TASK-015 的未通过项，不通过修改数据集或指标掩盖。

---

## 6. Agent 评估结果

数据集：

```text
version: task015-agent-v1
cases: 30
real DeepSeek samples: 10
```

真实 DeepSeek：

```text
model: deepseek-chat
prompt_version: task006-v2
passed: 10
failed: 0
token_usage: unavailable_from_chat_api
```

Fake LLM：

- 现有确定性测试覆盖 Intent、Tool、参数、权限、Confirm、Guardrail；
- Fake 通过率没有当作真实模型准确率；
- 30 条中其余 20 条未做真实模型执行。

---

## 7. 测试数据与数据库

```text
users=0
products=0
orders=0
knowledge_documents=0
```

- 测试数据已按 TASK015 运行 ID 清理；
- 没有整库清空；
- 没有新增 migration；
- 没有修改数据库结构；
- Docker 开发库当前为空。

---

## 8. 文件变更

### 新增

```text
agent/tests/security/test_task015_security.py
backend/tests/security/test_task015_payment_security.py
backend/tests/evaluation/task015_rag_eval_dataset.json
agent/tests/evaluation/task015_agent_cases.json
backend/scripts/task015_agent_eval.py
docs/04-testing/TASK-015/（测试计划、数据规范、支付/RAG/Agent 方案和报告）
docs/03-delivery/TASK-015/TASK-015-最终验收报告.md
```

### 修改

```text
backend/scripts/evaluate_rag.py        # 增加 answerable/no-answer/keyword 指标
backend/scripts/task014_e2e_seed.py    # E2E_PREFIX、TASK015 数据、清理修复
frontend/e2e/core.spec.ts              # 分类创建断言
frontend/e2e/knowledge.spec.ts         # 新版本上传断言
frontend/src/pages/knowledge/KnowledgeDetail.tsx # 上传 File 兼容修复
README.md
docs/README.md
docs/PROJECT-STATUS.md
```

### 未修改

```text
订单、支付、库存、售后业务规则
Agent Graph / Prompt / Tool 行为
RAG 检索策略和阈值
数据库结构
```

---

## 9. Git 和部署

```text
branch: feature/task-004-order
HEAD:   7d3b836
staged: 0
commit/push/reset/clean: 未执行
```

TASK-015 没有修改 Dockerfile/Compose，未重建生产镜像；开发 Docker 栈运行正常。

---

## 10. 未验证/未通过清单

1. 真实支付宝沙箱支付、通知、退款、退款查询：SKIPPED_CREDENTIALS。
2. RAG No-answer Accuracy = 0：检索无答案阈值。
3. RAG 精确 Chunk Recall 和 ACL 数据集：未验证。
4. Agent 真实模型只抽样 10/30。
5. 真实模型 Token 用量和完整 Tool Call 审计：不可得。
6. 浏览器 XSS/localStorage 运行时扫描：未做。
7. 生产部署/Nginx/HTTPS：属于 TASK-016/017。

## 11. 验收判定

```text
TASK-015 工程实施：完成
TASK-015 自动化回归：通过
TASK-015 真实支付沙箱：未验证
TASK-015 RAG 无答案指标：未通过
TASK-015 Agent 全量真实评估：部分完成
```

TASK-016 尚未开始。
