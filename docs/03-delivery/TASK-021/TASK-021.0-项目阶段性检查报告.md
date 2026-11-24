# TASK-021.0 项目阶段性检查报告

> 日期：2026-11-17  
> 性质：只读盘点；未删除数据、未清理 Volume、未修改业务代码  
> 当前分支：`main`  
> 当前 HEAD：`c732cc1 merge: complete TASK-001 to TASK-016 into main`

## 1. Git 状态

### 1.1 分支与 HEAD

```text
branch: main
HEAD:   c732cc1 merge: complete TASK-001 to TASK-016 into main
origin: https://github.com/hqw77/E-Commerce-Agent.git
remote: origin/main 与本地 main 同步
```

### 1.2 工作区统计

```text
staged:     0
unstaged:   16 modified files
untracked:  16 files（9 个路径项，其中若干为目录）
deleted:    0
renamed:    0
```

没有发现意外删除或文件覆盖。

### 1.3 修改文件

```text
agent/context.py
agent/graph.py
agent/nodes.py
agent/prompts.py
agent/routing.py
agent/runtime.py
agent/state.py
agent/tests/test_agent_api.py
agent/tools/context.py
agent/tools/executor.py
agent/tools/registry.py
backend/app/api/v1/agent.py
backend/app/schemas/agent.py
frontend/e2e/agent.spec.ts
frontend/e2e/core.spec.ts
frontend/e2e/knowledge.spec.ts
```

变更规模约：

```text
614 insertions
47 deletions
```

### 1.4 未跟踪文件

```text
agent/observability/
agent/safety/
agent/tests/test_trace.py
docs/02-design/TASK-019-Agent-现状架构分析.md
docs/02-design/TASK-019-Agent-目标架构设计.md
docs/02-design/TASK-019-Agent-重构实施计划.md
docs/03-delivery/TASK-019/
docs/03-delivery/TASK-020/
frontend/e2e/zz-agent-rag.spec.ts
```

TASK-019/020 的代码和文档**尚未提交**。

### 1.5 目录迁移和风险

当前工作区没有新的 `D`/`R` 状态。此前的 backend/agent 目录迁移已经包含在 HEAD `c732cc1` 中，不属于本次未提交变更。

风险：

- 16 个修改文件和 TASK-019/020 新增文件均未提交；
- 如果工作区被误清理，TASK-019/020 代码和报告会丢失；
- 本轮禁止 commit，因此暂时保留现状。

## 2. 开发数据库测试数据

数据源：开发 Docker MySQL `127.0.0.1:3307`，数据库 `ecommerce_agent`。

### 2.1 总数量

| 表 | 数量 |
|---|---:|
| `users` | 3 |
| `categories` | 2 |
| `products` | 1 |
| `skus` | 1 |
| `inventory` | 1 |
| `inventory_transactions` | 5 |
| `orders` | 2 |
| `after_sales` | 0 |
| `payments` | 0 |
| `knowledge_documents` | 1 |
| `knowledge_document_versions` | 2 |
| `knowledge_chunks` | 2 |

### 2.2 用户

| ID | 邮箱 | 管理员 | 归属 |
|---:|---|---|---|
| 18 | `qingfen77@gmail.com` | 是 | 用户手工创建，**保留** |
| 23 | `task015-admin-b775b99fd7@example.com` | 是 | TASK-015/020 E2E 测试 |
| 24 | `task015-user-23be1a1f09@example.com` | 否 | TASK-015/020 E2E 测试 |

### 2.3 商品、SKU、库存

| 表 | ID | 标识 | 关联 |
|---|---:|---|---|
| 分类 | 17 | `TASK015-CAT-bf9aed57-edited` | 商品 13 |
| 分类 | 18 | `TASK015-UI-75b2d661a9364aa99c62725780703f28` | 无商品 |
| 商品 | 13 | `TASK015-P-50DCBC4C` | 分类 17 |
| SKU | 13 | `TASK015-SKU-41066E61` | 商品 13 |
| 库存 | 13 | SKU 13 | total=6, reserved=1 |
| 库存流水 | 5 条 | SKU 13 | 入库/订单预占等 |

### 2.4 订单

| ID | 订单号 | 用户 | 状态 | 支付状态 | 金额 |
|---:|---|---:|---|---|---:|
| 13 | `ORD202611171213118B357EAD` | 24 | CANCELLED | UNPAID | 19.90 |
| 14 | `ORD20261117121408F52FB009` | 24 | PENDING_PAYMENT | UNPAID | 19.90 |

- 订单 13 是 E2E Agent Prepare/Confirm 取消的订单；
- 订单 14 是 TASK-020.A Trace WORKFLOW 样例创建的待支付订单；
- 当前没有售后记录，也没有支付记录。

### 2.5 知识库

| 对象 | 值 |
|---|---|
| 文档 ID | 11 |
| 标题 | `TASK015-KB-f4a75add` |
| visibility | PUBLIC |
| status | ACTIVE |
| created_by | 用户 23 |
| current_published_version_id | 17 |
| 版本 17 | PUBLISHED，chunk_count=1 |
| 版本 18 | INDEXED，chunk_count=1 |
| Chunk | 2 条 |

### 2.6 测试标识

可以明确归属 TASK-015/020.A 的测试数据：

```text
用户：23、24
分类：17、18
商品：13
SKU：13
库存：13
订单：13、14
知识文档：11，版本 17、18
Chunk：2
```

### 2.7 需保留的数据

```text
用户 18：qingfen77@gmail.com（用户手工创建的管理员）
```

### 2.8 不确定记录

- 分类 18 是 E2E 创建后未清理的 UI 测试分类；
- 订单 14 是 TASK-020.A Trace 样例的 WORKFLOW 测试订单，不是业务订单；
- 知识文档 11 是 TASK-015/020 E2E 测试文档；
- 当前数据库没有无法归属的生产业务数据。

本轮没有删除任何记录。

## 3. RAG 当前状态

### 3.1 数据库

```text
documents: 1
versions:  2
chunks:    2
```

文档 11：

```text
PUBLIC / ACTIVE
当前发布版本：17
版本 17：PUBLISHED
版本 18：INDEXED
```

### 3.2 Qdrant

```text
collection: knowledge_chunks_bge_m3_v1
status: green
points_count: 2
indexed_vectors_count: 0
```

注意：

- points_count=2，查询可用；
- `indexed_vectors_count=0` 是当前观察到的 Qdrant 状态，需要 TASK-021.1 确认是否为索引阈值/segment 状态，而不是直接修改配置。

### 3.3 上传文件

本地后端使用宿主目录：

```text
D:/github_repository/E-ecommerce-agent/storage/knowledge
```

当前文件：

```text
7 个 .md 文件
约 5,551 bytes
```

这些是 TASK-015/020 E2E 上传的测试文件，不是生产用户上传。

### 3.4 当前检索实测

使用开发环境管理员身份：

```text
查询：退款申请窗口是多少天？
结果：1 条
文档：TASK015-KB-f4a75add
score：0.7292655
```

无答案近似问题：

```text
查询：今天杭州市天气和温度是多少？
结果：1 条
文档：TASK015-KB-f4a75add
score：0.31758288
```

说明当前检索层没有阈值，低相关文档仍会返回。

### 3.5 RAG 评测集和基线

数据集：

```text
backend/tests/evaluation/task015_rag_eval_dataset.json
```

结果：

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

### 3.6 No-answer 失败样例

```text
今天杭州市的天气和温度是多少？ -> 商品使用说明 / 配送政策
公司年会在哪一天举行？ -> 配送政策 / 商品使用说明
如何申请退款到区块链钱包？ -> 退款规则 / 退货规则
明天股票市场会涨吗？ -> 配送政策 / 退款规则
火星基地什么时候开放？ -> 配送政策 / 换货规则
订单支持使用狗狗币支付吗？ -> 配送政策 / 退款规则
店铺是否提供二十四小时无人机配送？ -> 配送政策 / 退货规则
会员积分的个人所得税税率是多少？ -> 配送政策 / 退款规则
```

结果文件：

```text
docs/04-testing/TASK-015/rag-evaluation/task015-rag-results.json
```

这些样例可用于后续分析：

- 按 top score 分布选择阈值；
- 分析无答案与低分文档的关系；
- 设计 answerability / rerank；
- 保留现有数据集，不覆盖 TASK-005 历史。

本轮没有修改检索阈值、重排、召回参数或评测数据。

## 4. Docker 环境

### 4.1 开发环境

运行：

```text
mysql    Up (healthy)   127.0.0.1:3307 -> 3306
redis    Up (healthy)   127.0.0.1:6380 -> 6379
qdrant   Up             127.0.0.1:6333
```

本地 Backend：

```text
http://127.0.0.1:8000
```

本地 Frontend：

```text
http://127.0.0.1:5173
```

开发 Compose 中的 app 容器当前未运行；Backend 使用本地 Uvicorn。

### 4.2 生产环境

生产 Compose 当前全部停止：

```text
ecommerce-agent-prod-app-1      Exited
ecommerce-agent-prod-nginx-1    Exited
ecommerce-agent-prod-migrate-1  Exited
ecommerce-agent-prod-mysql-1    Exited
ecommerce-agent-prod-redis-1    Exited
ecommerce-agent-prod-qdrant-1   Exited
```

`127.0.0.1:8080` 未监听。

### 4.3 Volume

```text
ecommerce-agent-prod_model_cache_prod
ecommerce-agent-prod_mysql_data_prod
ecommerce-agent-prod_qdrant_data_prod
ecommerce-agent-prod_redis_data_prod
ecommerce-agent-prod_uploads_data_prod
e-ecommerce-agent_mysql_data
e-ecommerce-agent_qdrant_data
e-ecommerce-agent_redis_data
```

生产模型缓存：

```text
8.5GB
64 files
```

开发模型缓存：

```text
D:/github_repository/E-ecommerce-agent/.cache/huggingface
18.2GB 表观大小
64 files
```

开发环境当前没有独立的 uploads Docker Volume；上传文件在宿主机 `storage/knowledge`。

### 4.4 镜像

```text
ecommerce-agent-prod-app:latest       2.35GB
ecommerce-agent-prod-migrate:latest   2.35GB
ecommerce-agent-prod-nginx:latest     75.4MB
e-ecommerce-agent-app:latest          2.35GB
```

未发现新的生产数据库重建或 Volume 清理。

## 5. 文档状态

### 5.1 当前文档

```text
README.md
docs/PROJECT-STATUS.md
docs/README.md
docs/03-delivery/TASK-015/
docs/03-delivery/TASK-016/
docs/03-delivery/TASK-019/
docs/03-delivery/TASK-020/
```

TASK-019/020 的文档存在，但尚未提交：

```text
docs/02-design/TASK-019-*.md
docs/03-delivery/TASK-019/
docs/03-delivery/TASK-020/
```

### 5.2 状态文档不一致

当前 `README.md`、`docs/PROJECT-STATUS.md`、`docs/README.md` 仍停留在 TASK-016：

- 没有 TASK-019 架构审查状态；
- 没有 TASK-020 Trace/Safety/三路编排状态；
- 没有 TASK-020.A E2E 最终状态；
- 仍写“TASK-017 是下一阶段”。

结论：**需要更新状态文档**，但本轮不修改历史验收结果。

### 5.3 TASK-017/018

没有发现 TASK-017/018 的设计或交付文档。

```text
TASK-017：未开始
TASK-018：未开始
```

## 6. 需要保留的数据

```text
用户 18：qingfen77@gmail.com（手工创建管理员）
```

以及：

- 现有开发数据库 Schema；
- 开发 MySQL/Redis/Qdrant Volume；
- 生产 5 个 Volume；
- 生产模型缓存 `model_cache_prod`；
- 本地 `.env` / `.env.production`；
- 原始 `.cache/huggingface`；
- TASK-019/020 未提交代码和文档。

## 7. 可确认属于测试的数据

```text
用户 23、24
分类 17、18
商品 13
SKU 13
库存 13
订单 13、14
知识文档 11
版本 17、18
Chunk 2 条
storage/knowledge 下 7 个测试 .md 文件
```

其中：

- 订单 13：E2E 取消流程；
- 订单 14：TASK-020.A Trace WORKFLOW 样例；
- 分类 18：E2E UI 创建但未清理；
- 知识文档 11：E2E 测试知识库。

## 8. 存在不确定性的记录

- `indexed_vectors_count=0` 但 `points_count=2`，需要 TASK-021.1 进一步确认；
- 开发库当前的测试数据是否保留到 RAG 专项，需要业务/测试负责人决定；
- 生产 Volume 中上次 TASK-016 测试数据是否保留，需要单独确认；
- TASK-019/020 代码未提交，存在工作区丢失风险；
- 开发环境上传文件在宿主机而非 Docker Volume，与生产环境不一致。

## 9. 后续 RAG 优化建议

本阶段不实施，仅建议：

1. **阈值分析**
   - 对可回答问题、无答案问题统计 top score 分布；
   - 选择一个可解释的阈值，不要仅凭单个样例拍脑袋。

2. **无答案策略**
   - 检索为空、低分、答案覆盖不足分别处理；
   - 明确“知识库没有足够依据”的回答路径；
   - 不改变现有 Backend 权限和 Source 权威性。

3. **Rerank**
   - 对 BGE-M3 Top-K 候选做轻量 rerank；
   - 保留现有数据集和 TASK-005 历史结果。

4. **Chunk 质量**
   - 检查当前 1 chunk/version 的文档切分；
   - 增加精确 Chunk Recall 评估；
   - 增加 ADMIN_ONLY ACL 检索评估。

5. **Qdrant 一致性**
   - 确认 `indexed_vectors_count=0` 的含义；
   - 检查 collection 索引状态和 points 的实际可用性；
   - 不改阈值/参数前先建立基线。

6. **评测拆分**
   - 可回答、无答案、低置信度、ACL 分开统计；
   - 不覆盖 TASK-005 历史。

## 10. 风险和待处理事项

| 风险/事项 | 等级 | 建议 |
|---|---|---|
| TASK-019/020 代码和文档未提交 | 高 | 人工验收后统一提交，本轮不执行 |
| 开发库测试数据未清理 | 中 | TASK-021.1 前确定保留/清理策略 |
| 订单 14 是 Trace 测试订单 | 低 | 标记为测试，不纳入业务统计 |
| 分类 18 是未清理 E2E 分类 | 低 | 同上 |
| RAG No-answer Accuracy = 0 | 高 | 进入 TASK-021.1 专项 |
| Qdrant indexed_vectors_count=0 | 中 | 先诊断索引状态，不直接改参数 |
| 开发上传文件在宿主机 | 中 | 后续统一 dev/prod 存储语义 |
| 生产 Compose 停止 | 低 | 本阶段不启动；TASK-017 再处理 |
| 状态文档停留在 TASK-016 | 中 | 验收后更新状态文档 |
| TraceBuffer 进程内、重启丢失 | 中 | TASK-021 不扩展；后续单独评估 |
| 真实支付沙箱未验证 | 高 | 仍是 TASK-015 延期项 |
| TASK-017/018 未开始 | — | 不在本阶段范围 |

## 11. 本轮结论

```text
TASK-021.0：只读盘点完成
未删除数据
未清理 Volume
未修改业务代码
未修改 Schema
未修改 RAG 参数
未 commit/push/reset/clean
```

建议在进入 TASK-021.1 前先确认：

1. TASK-019/020 是否先提交；
2. TASK-015/020.A 测试数据是否保留；
3. 是否允许在 TASK-021.1 做 RAG 阈值/无答案策略的受控实验。
