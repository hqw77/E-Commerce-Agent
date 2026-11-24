# TASK-021.2 最终验收报告

> 日期：2026-11-17  
> 范围：TASK-021.2.1～021.2.4  
> 性质：RAG 无答案识别机制实施与回归验收  
> 约束：未删除测试数据、未清理 Volume、未修改生产 Docker 配置、未执行 Git commit/push/reset/clean

## 1. 总体结论

TASK-021.2 已完成：

```text
021.2.1  扩充版本化评测集、诊断 Qdrant 索引、建立基线
021.2.2  实施 score-band + lexical-evidence 无答案策略
021.2.3  接入 Agent RAG 流程，保留 ACL/Source/Untrusted/Trace
021.2.4  完成 RAG 评测、Backend/Agent 回归、静态检查、前端检查
```

最终结果：

```text
Backend/Agent pytest: 372 passed
Ruff: passed
Mypy: 137 source files, no issues
Alembic: no new operations
Frontend typecheck: passed
Frontend lint: passed
Vitest: 6 passed
Frontend build: passed
```

RAG 新评测集：

```text
版本：task0212-rag-v1
文档：6（5 PUBLIC + 1 ADMIN_ONLY）
问题：43
可回答：31（含 1 条 ACL 管理场景）
无答案：12
```

PUBLIC 用户正常问题：

```text
正常问题：42（30 可回答 + 12 无答案）
无答案拒绝：12/12 = 100%
可回答接受：30/30 = 100%
误拒：0
```

ACL：

```text
PUBLIC 用户访问 ADMIN_ONLY 问题：1/1 被 ACL 过滤
管理员访问同问题：1/1 在权限范围内，并可正常接受
```

## 2. 完整修改文件清单

### 新增

```text
agent/rag_evidence.py
agent/tests/test_rag_evidence.py
backend/scripts/task0212_rag_eval.py
backend/tests/evaluation/task0212_rag_eval_dataset.json
backend/tests/evaluation/knowledge/task0212_internal.md
backend/tests/services/test_retrieval_diagnostics.py
docs/03-delivery/TASK-021/task0212-rag-eval-results.json
docs/03-delivery/TASK-021/TASK-021.2-最终验收报告.md
```

### 修改

```text
backend/app/core/config.py
backend/app/services/rag/retrieval_service.py
agent/nodes.py
agent/tests/test_runtime.py
agent/tests/test_trace.py
```

### 未修改

```text
TASK-005 / TASK-015 历史评测集
正式 RAG 检索阈值以外的旧行为
Qdrant Collection 配置
数据库 Schema / Alembic migration
订单、支付、库存、售后业务规则
Agent GENERAL / TOOL / WORKFLOW 路由
TASK-020 Trace / Safety 结构
生产 Docker Compose
```

## 3. TASK-021.2.1：评测数据和基线

### 3.1 版本化评测集

旧数据集保持原样：

```text
backend/tests/evaluation/task015_rag_eval_dataset.json
version: task015-rag-v1
33 questions
```

新数据集：

```text
backend/tests/evaluation/task0212_rag_eval_dataset.json
version: task0212-rag-v1
supersedes: task015-rag-v1
```

新增内容：

```text
5 条可回答近义问题
4 条无答案问题
1 条 ADMIN_ONLY ACL 场景
5 篇原有 PUBLIC 文档
1 篇 ADMIN_ONLY 文档 task0212_internal.md
```

不覆盖旧数据集，不修改旧结果文件。

### 3.2 新数据集字段

每条问题包含：

```text
id
question
expected_document
expected_keywords
answerable
visibility
required_role
category
```

评测输出每条 query 保存：

```text
Top-K document_id
Top-K chunk_id
Top-K document_title
Top-K similarity score
expected_document
access_denied
accepted
reason
top_score
evidence_coverage
```

离线脚本使用合成文档/Chunk ID（`document_id=1..6`、`chunk_id=1001..1006`），不是数据库 ID；报告明确区分。

### 3.3 Qdrant 索引状态诊断

当前 Qdrant：

```text
collection: knowledge_chunks_bge_m3_v1
status: green
points_count: 2
indexed_vectors_count: 0
segments_count: 8
hnsw_config.indexing_threshold: 10000
```

结论：

- 这不是 Collection 损坏；
- 2 个 Point 远低于 HNSW 索引阈值 10000；
- Qdrant 对低于阈值的 Collection 使用可用的精确/暴力搜索路径；
- 当前 2 个 Point 的查询可用；
- 没有重建 Collection，没有删除 Point，没有修改持久化数据；
- 不能据此把当前 2 Point 状态当作生产性能基线。

## 4. TASK-021.2.2：无答案策略

### 4.1 策略

文件：

```text
agent/rag_evidence.py
```

策略名称：

```text
score-band + lexical-evidence
```

配置默认值：

```text
agent_rag_min_score = 0.60
agent_rag_high_confidence_score = 0.625
agent_rag_min_evidence_coverage = 0.50
```

判断逻辑：

```text
1. 无检索结果 -> NO_RETRIEVAL / NO_ALLOWED_DOCUMENTS / NO_CANDIDATES
2. top_score < 0.60 -> LOW_SCORE
3. 0.60 <= top_score < 0.625
   且 lexical evidence coverage < 0.50 -> LOW_EVIDENCE
4. 其他 -> ACCEPTED
```

没有把 TASK-021.1 的 0.61 直接写成正式阈值。

### 4.2 Lexical evidence

实现：

```text
中文 2-gram
+ 英数字 token
+ 停用词表
+ top1 chunk 覆盖率
```

不增加模型调用、不增加向量调用、不引入新 tokenizer 依赖。

局限：

- 只是词面证据，不是语义蕴含；
- 同义词、改写、跨语言查询可能低覆盖；
- 因此只用于“低分模糊区间”，不作为所有问题的唯一门槛。

### 4.3 空结果原因

`RetrievalOutcome` 新增：

```text
NO_ALLOWED_DOCUMENTS：无权限范围内文档（ACL/空知识库）
NO_CANDIDATES：有权限但没有向量候选
OK：有候选
```

检索失败仍由 `RAG_RETRIEVAL_UNAVAILABLE` / HTTP 503 表达，不混同为无答案。

### 4.4 不改变原始检索 API

`/api/v1/knowledge/retrieve` 仍返回原始 Top-K。

无答案策略只在 Agent RAG 边界应用：

- 保留知识库调试/评测能力；
- 不改变既有知识库 API 语义；
- 不让普通 UI 检索结果突然变空。

## 5. TASK-021.2.3：Agent RAG 接入

`agent/nodes.py::retrieve_knowledge_node`：

1. 调用 `retrieve_with_diagnostics`（如果实现存在）；
2. 兼容测试 double 的 `retrieve` 回退；
3. 应用 `evaluate_rag_evidence`；
4. 不通过时清空 `retrieved_items`；
5. `knowledge_answer_node` 返回 `NO_KNOWLEDGE_ANSWER`；
6. 不调用生成模型；
7. 不构造 Source；
8. 写入 `rag_retrieval` 和 `rag_decision` Trace 事件。

保持：

- CurrentUser 身份；
- PUBLIC / ADMIN_ONLY 预过滤；
- MySQL 权威校验；
- Source 服务端构造；
- RAG 内容 untrusted；
- TASK-020 Trace / Safety；
- GENERAL / TOOL / WORKFLOW 路由不变。

## 6. 评测结果

### 6.1 TASK-015 历史结果

历史结果：

```text
Recall@5:              1.0
Precision@5:           0.2
MRR:                   1.0
Empty Retrieval Rate:  0.0
No-answer Accuracy:    0.0
Chunk Keyword Hit:     1.0
queries:               33
answerable:            25
no_answer:             8
```

历史结果来自真实 Qdrant + TASK-015 的 5 篇临时评测文档。

### 6.2 TASK-021.2 新结果

新数据集离线评测（不是当前 Qdrant 的 2 Point 线上结果）：

```text
task0212-rag-v1
6 文档
43 问题
31 可回答（含 ACL 1）
12 无答案
```

PUBLIC 用户正常问题：

| 指标 | 值 |
|---|---:|
| 可回答问题 | 30 |
| 无答案问题 | 12 |
| 无答案拒绝率 | 100% |
| 可回答接受率 | 100% |
| 误拒数 | 0 |
| 误拒率 | 0% |

旧 33 题子集：

| 指标 | 值 |
|---|---:|
| 可回答问题 | 25 |
| 无答案问题 | 8 |
| 无答案拒绝率 | 100% |
| 可回答接受率 | 100% |
| 误拒 | 0 |

Top-1：

```text
可回答 Top-1 命中：30/30
```

### 6.3 指标对比的正确方式

不能直接混用：

```text
TASK-015：真实 Qdrant，5 篇临时文档，原始 Top-K
TASK-021.2：离线 BGE-M3 内存复算，6 篇评测文档，策略决策
```

可比的部分：

```text
同一历史 33 题子集
旧基线 No-answer Accuracy 0%
新策略在旧子集上 8/8 无答案拒绝、25/25 可回答接受
```

不可比的部分：

```text
TASK-015 Precision@5=0.2 与新策略 100% 接受率不是同一指标
新数据集的 43 题规模和历史 33 题不同
当前线上只有 1 个文档 / 2 个 Chunk，不能代表新数据集
```

### 6.4 可信度限制

```text
无答案问题：12
可回答正常问题：30
总计：42
```

Wilson 95% 区间：

```text
无答案拒绝：0.7575 ～ 1.000
可回答接受：0.8865 ～ 1.000
```

样本仍然小，且阈值在评测集上得到，存在过拟合风险。

## 7. 测试结果

### 7.1 Backend/Agent

```text
372 passed in 17.73s
```

新增测试：

```text
agent/tests/test_rag_evidence.py           10
agent/tests/test_runtime.py                1
backend/tests/services/test_retrieval_diagnostics.py 3
```

覆盖：

- 空结果；
- LOW_SCORE；
- LOW_EVIDENCE；
- score band 边界；
- ACCEPTED；
- 无答案时不再调用生成模型；
- `rag_decision` Trace；
- `NO_ALLOWED_DOCUMENTS` / `NO_CANDIDATES` / `OK` 诊断；
- 旧 Agent/RAG/Trace 测试全部保持。

### 7.2 静态检查

```text
Ruff: passed
Mypy: 137 source files, no issues
Alembic check: no new operations
```

### 7.3 前端

本轮没有修改前端代码；仍执行：

```text
typecheck: passed
lint: passed
Vitest: 6 passed
build: passed
```

### 7.4 未执行

- 未执行生产 Qdrant 重建；
- 未执行真实线上流量压测；
- 未执行 TASK-022；
- 未执行真实支付。

## 8. 已知限制和遗留问题

1. **当前线上知识库极小**：1 文档、2 Chunk；新策略的离线评测使用 6 文档、43 题，不代表生产分布。
2. **样本量小**：12 条无答案、30 条正常可回答，Wilson 区间宽。
3. **指标过于理想**：100% 无答案拒绝 + 100% 可回答接受，存在明显过拟合风险，不能当作生产验收。
4. **Lexical evidence 局限**：同义词、改写、跨语言查询可能被误拒。
5. **阈值仍需评审**：0.60 / 0.625 / 0.50 是离线候选，不是生产认证。
6. **原始 `/knowledge/retrieve` 仍返回低分文档**：无答案策略只在 Agent 边界生效，保留调试 API 原始语义。
7. **ACL 诊断粒度有限**：`NO_ALLOWED_DOCUMENTS` 不能区分“没有已发布文档”和“全部被 ACL 过滤”。
8. **Qdrant `indexed_vectors_count=0`**：当前是低于 HNSW 索引阈值，不是损坏；不能据此做性能结论。
9. **离线合成 ID**：评测 Top-K 文档/Chunk ID 不是数据库 ID。
10. **未做多轮/长上下文 RAG 评测**。
11. **未删除 TASK-015/020.A 遗留测试数据**，遵守本轮禁止删除要求。

## 9. 后续建议

1. 用真实知识库扩充 100+ 可回答/无答案样本，再复核阈值。
2. 保存线上 query 的 top-k score（脱敏）用于分布监控，不要记录内容或个人信息。
3. 为 ADMIN_ONLY 建立独立 ACL 评测集，不应混入普通无答案指标。
4. 对近义/改写问题评估语义 answerability 或 rerank，但不能无证据引入额外模型调用。
5. 在正式启用前做灰度和误拒监控；当前策略默认值仍应视为候选配置。
6. 继续保留 TASK-015 历史结果，不覆盖。

## 10. Git 状态

```text
branch: main
HEAD:   c732cc1
staged: 0
commit/push/reset/clean: 未执行
```

TASK-019/020/021 的代码、评测数据和报告仍未提交，保持工作区现状。

## 11. 验收判定

```text
TASK-021.2.1：完成
TASK-021.2.2：完成
TASK-021.2.3：完成
TASK-021.2.4：完成
自动化回归：通过
生产阈值：未认定
```

本轮完成，停止，不开始 TASK-021.3 或 TASK-022，等待人工验收。

### 4.5 四类结果如何区分

| 类别 | 判定来源 | 结果 |
|---|---|---|
| 检索失败 | Embedding/Qdrant 抛错 | `RAG_RETRIEVAL_UNAVAILABLE`，HTTP 503，不伪装成无答案 |
| 权限过滤 | `list_retrievable_versions` 为空 | `NO_ALLOWED_DOCUMENTS`，ACL 场景 |
| 检索无候选 | 向量检索无候选或 MySQL 无有效行 | `NO_CANDIDATES` |
| 证据不足 | 有候选但分数/证据覆盖不足 | `LOW_SCORE` 或 `LOW_EVIDENCE` |
| 真正无答案问题 | 评测标签 `answerable=false` 且被策略拒绝 | 计入 No-answer rejection |
| 可回答 | 策略接受并进入生成 | `ACCEPTED` |

说明：

- “权限过滤”和“真正无答案”在最终用户侧都不应泄露内部文档；
- 二者在服务端诊断和评测统计中必须分开；
- 当前 `NO_ALLOWED_DOCUMENTS` 同时覆盖“没有已发布文档”和“全部被 ACL 过滤”，这是已知粒度限制。
