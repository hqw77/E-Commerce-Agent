# TASK-015 RAG 评估方案

> 数据集版本：`task015-rag-v1`  
> 不复用/覆盖 TASK-005 的历史结果。

## 1. 现状

```text
backend/scripts/evaluate_rag.py
backend/tests/evaluation/rag_eval_dataset.json
docs/03-delivery/TASK-005/rag-evaluation-results.json
```

现有数据集：

```text
documents: 5
questions: 25
```

现有指标：

- Recall@5
- Precision@5
- MRR
- Empty Retrieval Rate

历史基线：

```text
Recall@5 = 1.0
MRR = 1.0
Precision@5 = 0.2
Empty Retrieval Rate = 0.0
```

## 2. 缺口

- 没有无答案问题；
- 没有“相似但无直接答案”问题；
- 没有 `No-answer Accuracy`；
- 没有 Chunk 级评估；
- 没有权限受限问题的独立结果；
- 当前结果不能直接作为 TASK-015 新数据集结果。

## 3. 新数据集

新建独立文件：

```text
backend/tests/evaluation/task015_rag_eval_dataset.json
```

结构：

```json
{
  "version": "task015-rag-v1",
  "documents": [],
  "questions": [
    {
      "id": "T15-RAG-001",
      "question": "...",
      "answerable": true,
      "expected_document": "TASK015-...",
      "expected_chunk_ids": [],
      "visibility": "PUBLIC",
      "category": "refund|shipping|product|policy"
    }
  ]
}
```

覆盖：

- 原有可回答问题（复用问题，不直接覆盖旧文件）；
- 同义表达；
- 跨文档问题；
- 相似但无直接答案；
- 完全无答案；
- `ADMIN_ONLY` 权限受限；
- 恶意指令文档（安全集，不混入正常指标）。

目标规模：

```text
可回答：25
无答案/相似无答案：8～10
权限受限：3～5
```

## 4. 指标

必须输出：

```text
Recall@K
Precision@K
MRR
Empty Retrieval Rate
No-answer Accuracy
Chunk Recall@K（有 expected_chunk_ids 时）
ACL Leakage Rate（权限受限问题）
```

定义：

- **No-answer Accuracy**：无答案问题中，系统明确返回“不知道/无依据”的比例；
- **ACL Leakage Rate**：普通用户检索到 ADMIN_ONLY 文档的比例，必须为 0；
- **Chunk Recall@K**：预期 chunk 是否出现在 Top-K。

## 5. 配置记录

每次评估必须记录：

```text
dataset_version
embedding_model
embedding_dimension
qdrant_collection
top_k
threshold（如有）
document_count
question_count
run_at
```

## 6. 执行方式

```powershell
$env:PYTHONPATH="$PWD\backend;$PWD"
.venv\Scripts\python.exe backend/scripts/evaluate_rag.py `
  --dataset backend/tests/evaluation/task015_rag_eval_dataset.json `
  --output docs/04-testing/TASK-015/rag-evaluation/task015-rag-results.json
```

需要先准备独立测试知识文档并索引，不能把旧 TASK-005 测试文档当作新结果。

## 7. 输出

```text
docs/04-testing/TASK-015/rag-evaluation/
├── dataset-task015-rag-v1.json
├── task015-rag-results.json
└── TASK-015-RAG评估报告.md
```

TASK-005 结果保持原样，不覆盖。

## 8. 通过标准

- 新数据集实际执行；
- 无答案场景有可解释结果；
- 权限受限文档不泄露；
- 记录模型、collection、Top-K 和数据集版本；
- 不删除困难问题来提高指标；
- 不将 Mock/Fake 检索结果标记为真实 RAG 评估。
