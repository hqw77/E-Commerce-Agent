# TASK-015 RAG 评估报告

> 数据集版本：`task015-rag-v1`  
> 运行时间：2026-11-17  
> 历史 TASK-005 数据未被覆盖。

## 1. 配置

```text
embedding_model: BAAI/bge-m3
embedding_dimension: 1024
collection: knowledge_chunks_bge_m3_v1
top_k: 5
documents: 5
questions: 33
answerable: 25
no_answer: 8
```

结果文件：

[TASK-015 RAG 结果](rag-evaluation/task015-rag-results.json)

## 2. 指标

```text
Recall@5:              1.0000
Precision@5:           0.2000
MRR:                   1.0000
Empty Retrieval Rate:  0.0000
No-answer Accuracy:    0.0000
Chunk Keyword Hit:     1.0000
Queries:               33
```

## 3. 结果解释

### 可回答问题

25 条全部命中预期文档，Recall@5=1、MRR=1。Precision@5=0.2 是因为每个问题返回 5 条，其中只有 1 条预期文档。

### 无答案问题

8 条无答案问题全部返回了相似文档，`No-answer Accuracy=0`。

示例：

```text
今天杭州市天气 → 商品使用说明 / 配送政策
如何退款到区块链钱包 → 退款规则 / 退货规则
火星基地什么时候开放 → 配送政策 / 换货规则
```

这说明当前 **Retrieval 层没有“无答案”阈值**，会返回 Top-K 相似文档；不能把“检索到文档”当作“有答案”。

### Chunk 级

`Chunk Keyword Hit=1.0` 是当前数据集按 `expected_keywords` 做关键词覆盖的弱指标，不等同于精确 Chunk Recall。数据集没有稳定的 `expected_chunk_ids`，不能宣称精确 Chunk 级通过。

### 权限

本次 RAG 自动评估使用管理员身份，不包含 ADMIN_ONLY 权限受限问题。知识库 ACL 由现有 Backend API 安全测试覆盖，但不在本数据集的指标中，属于未覆盖项。

## 4. 与 Agent 无答案回答的关系

Agent 真实抽样中，知识问题“退款需要满足什么条件”返回：

```text
知识库中没有找到足够依据来回答这个问题。
```

这说明 Agent 回答层有“无依据”表达，但 Retrieval 指标仍显示会返回相似文档。两者不能互相替代。

## 5. 结论

```text
可回答问题检索：VERIFIED
无答案检索：FAIL（No-answer Accuracy 0）
Chunk 精确评估：NOT_VERIFIED
ACL RAG 评估：NOT_VERIFIED（API ACL 测试另行覆盖）
```

未通过项是真实评估结果，不通过修改数据集或指标掩盖。

## 6. 建议

- 在 RAG 检索策略中增加相关性阈值/无答案判定（属于后续设计变更，不在 TASK-015 修改）；
- 增加稳定 `expected_chunk_ids` 和精确 Chunk Recall；
- 增加 ADMIN_ONLY 文档的普通用户检索评估；
- 保留本数据集版本和结果，不覆盖 TASK-005。
