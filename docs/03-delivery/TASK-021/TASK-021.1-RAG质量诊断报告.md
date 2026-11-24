# TASK-021.1 RAG 质量诊断报告

> 日期：2026-11-17  
> 性质：离线诊断与策略模拟  
> 约束：未修改正式 RAG 代码、运行时阈值、Qdrant Collection、数据库 Schema  
> 数据：未删除任何测试数据或 Docker Volume  
> Git：未执行 commit/push/reset/clean

## 1. 诊断结论

TASK-015 的 `No-answer Accuracy = 0` 不是单一“阈值没开”的问题，而是：

1. 当前 Retrieval 没有 no-answer 判定；
2. 无答案问题的 top1 分数与部分可回答问题的 top1 分数发生重叠；
3. 单纯加入绝对分数阈值能显著改善离线指标，但会产生可回答问题误拒；
4. top1-top2 margin 策略不适合作为主策略；
5. 当前评测只有 **33 题、25 条可回答、8 条无答案**，且离线语料是 **5 篇文档**，而线上当前只有 **1 篇文档、2 个 Chunk**，结论只能作为方向性证据，不能直接作为生产阈值。

离线最优分数阈值候选：

```text
threshold = 0.61（或 0.62）
No-answer Recall:        8/8 = 100%
Answerable Acceptance:   24/25 = 96%
Balanced Accuracy:       0.98
被误拒的可回答问题:      shipping-05
```

但这不是生产建议阈值；它是在 33 条历史样本上得到的离线结果。

## 2. 数据与规模

### 2.1 历史评测集

```text
数据集：backend/tests/evaluation/task015_rag_eval_dataset.json
版本：task015-rag-v1
文档：5
问题：33
可回答：25
无答案：8
```

历史结果：

```text
docs/04-testing/TASK-015/rag-evaluation/task015-rag-results.json
```

历史指标：

```text
Recall@5:              1.0
Precision@5:           0.2
MRR:                   1.0
Empty Retrieval Rate:  0.0
No-answer Accuracy:    0.0
Chunk Keyword Hit:     1.0
```

### 2.2 当前运行知识库

```text
文档：1
当前发布版本：17
版本：2（17 PUBLISHED，18 INDEXED）
Chunk：2
Qdrant points：2
Qdrant indexed_vectors_count：0
```

当前线上知识库与历史评测语料不是同一批文档：

- 历史评测：5 篇 `rag-eval-*` 文档；
- 当前开发库：1 篇 `TASK015-KB-f4a75add`，2 个 Chunk。

因此不能把本轮 33 题的结论直接解释为当前生产知识库的准确率。

### 2.3 样本规模限制

```text
无答案样本：8
可回答样本：25
总样本：33
```

8/8 无答案命中的 95% Wilson 区间约：

```text
0.676 ～ 1.000
```

24/25 可回答接受的 95% Wilson 区间约：

```text
0.805 ～ 0.993
```

区间很宽，说明 8 条无答案样本不足以证明阈值在生产分布上同样有效。

## 3. 离线复现方法

历史结果文件没有保存每个 query 的 score，因此不能直接读取阈值。

本次采用只读离线复现：

1. 读取 TASK-015 的 5 篇评测文档；
2. 使用现有 `BAAI/bge-m3` provider 生成 1024 维 normalized embedding；
3. 使用相同 33 个问题生成 query embedding；
4. 以 cosine 相似度在内存中排序；
5. 将离线 top-1 与历史结果对照；
6. 对 0.10～0.85 的绝对分数阈值做扫描；
7. 对 top1-top2 margin 做扫描；
8. 对 score + margin 联合策略做网格扫描。

脚本：

```text
backend/scripts/task0211_rag_diagnostic.py
```

结果：

```text
docs/03-delivery/TASK-021/task0211-rag-diagnostic.json
```

该脚本：

- 不连接 MySQL；
- 不连接 Qdrant；
- 不写应用数据库；
- 不修改 Collection；
- 不修改检索参数。

## 4. 离线复现校验

```text
top-1 与历史结果一致：32/33
top-5 文档集合与历史结果一致：33/33
可回答问题 top-1 命中：24/25
```

唯一 top-1 差异：

```text
return-04
问题：退货申请通过后如何填写物流单号？
离线 top1：退款规则 0.626253
离线 top2：退货规则 0.616098
历史 top1：退货规则
```

差异原因：

- 两个文档语义接近；
- 分数差距只有约 0.010；
- 历史结果没有保存 score，无法判断这是模型版本差异、索引版本差异还是 Qdrant 浮点/排序差异；
- top-5 集合完全一致，说明离线复现可用于方向性分析，但不能当作逐分数精确复刻。

## 5. 分数分布

### 5.1 top1 score

| 组别 | min | median | mean | max |
|---|---:|---:|---:|---:|
| 可回答 | 0.604212 | 0.675633 | 0.692307 | 0.778581 |
| 无答案 | 0.323224 | 0.439533 | 0.452677 | 0.604434 |

关键观察：

```text
可回答最低分：0.604212
无答案最高分：0.604434
差值仅：0.000222
```

这两类在边界上几乎重合：

- 可回答 `shipping-05` 为 0.604212；
- 无答案 `T15-RAG-NO-03` 为 0.604434；
- 一个绝对阈值无法同时做到“无答案全拒”和“可回答全收”。

### 5.2 分数判别能力

```text
ROC-AUC（用低分判定无答案）：0.995
```

AUC 很高，但只有 8 条无答案样本，不能过度解释。

### 5.3 top1-top2 margin

| 组别 | min | median | mean | max |
|---|---:|---:|---:|---:|
| 可回答 | 0.010155 | 0.103132 | 0.126575 | 0.377250 |
| 无答案 | 0.015966 | 0.053061 | 0.054771 | 0.090950 |

可回答问题中也存在 margin 很小的样本；margin 不能单独作为可靠策略。

## 6. 绝对分数阈值扫描

| threshold | No-answer Recall | Answerable Acceptance | Balanced Accuracy | 拒绝无答案 | 接受可回答 |
|---:|---:|---:|---:|---:|---:|
| 0.00（baseline） | 0.000 | 1.000 | 0.500 | 0/8 | 25/25 |
| 0.50 | 0.625 | 1.000 | 0.8125 | 5/8 | 25/25 |
| 0.55 | 0.750 | 1.000 | 0.8750 | 6/8 | 25/25 |
| 0.58 | 0.875 | 1.000 | 0.9375 | 7/8 | 25/25 |
| 0.60 | 0.875 | 1.000 | 0.9375 | 7/8 | 25/25 |
| **0.61** | **1.000** | **0.960** | **0.980** | **8/8** | **24/25** |
| 0.62 | 1.000 | 0.960 | 0.980 | 8/8 | 24/25 |
| 0.65 | 1.000 | 0.800 | 0.900 | 8/8 | 20/25 |
| 0.70 | 1.000 | 0.440 | 0.720 | 8/8 | 11/25 |

### 6.1 0.60 与 0.61 的差别

`0.60`：

- 拒绝 7/8 无答案；
- 接受全部 25 条可回答；
- 漏掉 `T15-RAG-NO-03`（0.604434）。

`0.61`：

- 拒绝全部 8 条无答案；
- 拒绝 1 条可回答（`shipping-05`，0.604212）；
- balanced accuracy 更高，但引入 false rejection。

这是典型的阈值权衡，不存在同时零误拒、零漏拒的切点。

## 7. Margin 策略

| margin threshold | No-answer Recall | Answerable Acceptance | Balanced Accuracy |
|---:|---:|---:|---:|
| 0.05 | 0.500 | 0.760 | 0.630 |
| 0.08 | 0.750 | 0.640 | 0.695 |
| 0.09 | 0.875 | 0.520 | 0.6975 |
| 0.095 | 1.000 | 0.520 | 0.760 |
| 0.10 | 1.000 | 0.520 | 0.760 |

结论：

- margin 可以识别部分无答案；
- 但要达到 100% 无答案拒绝，会误拒近一半可回答问题；
- margin 不适合作为唯一 no-answer 策略。

## 8. 策略对照

| 策略 | No-answer Recall | Answerable Acceptance | 评价 |
|---|---:|---:|---|
| 无策略，直接返回 top-k | 0.000 | 1.000 | 当前行为，No-answer Accuracy=0 |
| 绝对分数阈值 0.61 | 1.000 | 0.960 | 离线最佳 balanced；有 1 条误拒 |
| 绝对分数阈值 0.60 | 0.875 | 1.000 | 保守，漏 1 条无答案 |
| top1-top2 margin 0.095 | 1.000 | 0.520 | 误拒过多 |
| score + margin 联合 | 1.000 | 0.960 | 本数据上未优于单独 score |

本轮没有选择或实施正式阈值。

## 9. 失败样例诊断

### 9.1 无答案但仍被检索

```text
T15-RAG-NO-01 今天杭州市的天气和温度是多少？
top1 0.443568 商品使用说明

T15-RAG-NO-02 公司年会在哪一天举行？
top1 0.366771 配送政策

T15-RAG-NO-03 如何申请退款到区块链钱包？
top1 0.604434 退款规则

T15-RAG-NO-04 明天股票市场会涨吗？
top1 0.377211 配送政策

T15-RAG-NO-05 火星基地什么时候开放？
top1 0.323224 配送政策

T15-RAG-NO-06 订单支持使用狗狗币支付吗？
top1 0.515133 配送政策

T15-RAG-NO-07 店铺是否提供二十四小时无人机配送？
top1 0.555574 配送政策

T15-RAG-NO-08 会员积分的个人所得税税率是多少？
top1 0.435498 配送政策
```

按分数可分为：

- 明显低分：NO-01/02/04/05/08（0.32～0.44）；
- 中间分数：NO-06/07（0.51～0.56）；
- 边界高分：NO-03（0.6044，与可回答问题重叠）。

这说明仅靠一个统一阈值会主要被 NO-03 卡住。

### 9.2 被 0.61 误拒的可回答问题

```text
shipping-05
问题：发货后在哪里查看物流公司和运单号？
top1：配送政策 0.604212
top2：退款规则 0.484216
```

该问题语义与“物流/运单”相关，top1 虽然命中正确文档，但分数刚好低于阈值。

## 10. 当前知识库的限制

当前开发库实际只有：

```text
1 个文档
2 个 Chunk
Qdrant 2 points
```

而离线实验使用：

```text
5 个历史评测文档
33 个历史问题
```

因此：

1. 离线实验的 5 文档规模不能代表当前 1 文档知识库；
2. 33 题、8 条无答案不足以稳定估计阈值；
3. 当前线上没有足够的“无答案 + 可回答”混合样本；
4. 当前 Qdrant `indexed_vectors_count=0`，虽然 `points_count=2` 且查询可用，仍需单独确认索引状态；
5. 不能把 0.61 直接写入正式配置；
6. 不能根据本轮结果声称生产 No-answer Accuracy 已修复。

## 11. 对后续 RAG 优化的建议

### 优先级 P0：先扩充评测，不先改线上阈值

建议至少补充：

- 更多可回答问题；
- 更多无答案问题；
- 与当前知识库真实内容对应的问答；
- 近义/边界问题（如 NO-03）；
- ADMIN_ONLY / PUBLIC ACL 对照；
- 文档版本切换前后对照。

### P1：建立 offline-first 阈值实验

- 继续使用独立脚本；
- 在评测结果中保存 `top_k` 分数，而不仅是文档标题；
- 固定模型、collection、chunk 版本；
- 记录每次实验的 Git/数据版本；
- 对阈值扫描输出置信区间和误拒样例。

### P2：不要只用绝对分数

建议评估：

```text
score threshold
+ answerability / evidence coverage
+ document/version consistency
+ rerank
```

绝对阈值只能作为候选组件，不能作为唯一 no-answer 判定。

### P3：保持正式行为不变

本轮不修改：

- `agent` 的 RAG 路径；
- `KnowledgeRetrievalService`；
- `rag_top_k` / candidate 参数；
- Qdrant Collection；
- 数据库 Schema；
- 任何测试数据。

## 12. 风险与限制

| 风险 | 说明 |
|---|---|
| 样本量小 | 33 题、8 条无答案 |
| 语料与线上不一致 | 离线 5 文档，线上 1 文档/2 Chunk |
| 历史结果无分数 | 只能离线复现 |
| top-1 复现有 1 条差异 | `return-04` |
| 阈值过拟合 | 0.61 是在当前 8 条无答案上得到 |
| Qdrant 索引状态不明确 | `indexed_vectors_count=0` |
| 不能直接上线 | 本轮明确不修改生产检索 |
| 文档版本差异 | 发布版本 17 与 INDEXED 18 并存 |

## 13. 本轮产物

```text
backend/scripts/task0211_rag_diagnostic.py
docs/03-delivery/TASK-021/task0211-rag-diagnostic.json
docs/03-delivery/TASK-021/TASK-021.1-RAG质量诊断报告.md
```

## 14. 最终判定

```text
TASK-021.1 诊断：完成
正式 RAG 代码修改：无
运行时阈值修改：无
Qdrant Collection 修改：无
数据库 Schema 修改：无
测试数据删除：无
Git 操作：无
生产阈值建议：暂不实施
```

结论：

```text
0.61 是当前 33 条历史样本上的离线候选，
不是已验证的生产阈值。
下一步应先扩大评测集并保存逐 query 分数，
再决定是否进入正式 RAG 策略变更。
```

本报告完成后停止，不开始 TASK-021.2。

## 15. 产物与 Git 状态

本轮新增：

```text
backend/scripts/task0211_rag_diagnostic.py
docs/03-delivery/TASK-021/task0211-rag-diagnostic.json
docs/03-delivery/TASK-021/TASK-021.1-RAG质量诊断报告.md
```

没有修改：

```text
agent/ 正式 RAG 路径
backend/app/services/rag/
运行时检索参数
Qdrant Collection
数据库 Schema
Docker Compose / Volume
测试数据
```

Git：

```text
branch: main
HEAD:   c732cc1
commit/push/reset/clean: 未执行
```

TASK-019/020/021 相关未提交文件仍保留在工作区。

## 16. 当前运行态补充

TASK-021.0 曾实测当前 1 篇知识文档的检索：

```text
退款申请窗口是多少天？       top1 score 0.7292655
今天杭州市天气和温度是多少？ top1 score 0.31758288
```

这组数值只用于说明当前线上知识库也能产生低分无答案检索；由于当前只有 1 篇文档、2 个 Chunk，没有把它纳入 33 题历史阈值统计。
