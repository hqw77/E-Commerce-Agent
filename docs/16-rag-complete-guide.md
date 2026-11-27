# 16 RAG 完整教程与效果评估

这篇讲 RAG 的概念、项目实现、完整代码链、阅读方法、面试回答和真实效果。

先给结论：

作为面试 Demo，这套 RAG 是够用的。

作为生产系统，它还不够。

当前项目的 RAG 重点不是“向量数据库多强”，而是三件事：

```text
权限过滤
MySQL 回查
证据不足时拒答
```

---

# 第一部分：RAG 是什么

## 1. 一句话解释

RAG 是“先查资料，再让模型回答”。

不是让模型凭记忆回答，而是：

```text
用户问题
-> 检索相关知识
-> 把知识放进上下文
-> 模型基于知识回答
-> 返回来源
```

## 2. RAG 解决什么问题

大模型有三个问题：

```text
不知道企业私有知识
容易编造
知识可能过期
```

RAG 让模型回答前先看资料。

资料来自知识库，不由模型记忆决定。

## 3. RAG 的两个阶段

写入阶段：

```text
文档
-> 解析
-> 清洗
-> 切块
-> 向量化
-> 存 MySQL 和 Qdrant
```

查询阶段：

```text
问题
-> 向量化
-> 检索
-> 回查正文
-> 证据判断
-> 回答或拒答
```

## 4. RAG 和 Agent 的关系

RAG 是 Agent 的一条知识问答路径。

Agent 还有 Tool 路径，用来查订单、查库存、取消订单。

两者分工：

```text
RAG：政策、说明、规则类知识
Tool：实时业务数据和写操作
```

RAG 不能代替 Tool。

Tool 也不能代替 RAG。

---

# 第二部分：项目里的 RAG 架构

## 1. 三个存储各做什么

MySQL：

```text
文档
文档版本
Chunk 正文
权限字段
发布状态
```

Qdrant：

```text
Chunk 向量
chunk_id
document_id
version_id
embedding_model
```

文件存储：

```text
原始上传文件
```

关键边界：

```text
MySQL 是正文、版本和权限的权威源。
Qdrant 只是向量索引，不是权威源。
```

## 2. 为什么召回后还要回 MySQL

Qdrant 里的 point 可能过期：

```text
文档被删除
版本被替换
Chunk 被重建
权限发生变化
```

所以 Qdrant 召回后，必须用 chunk_id 回 MySQL 再查一次。

MySQL 查不到，就丢弃这个 point。

## 3. 当前配置

```text
Embedding：BAAI/bge-m3
维度：1024
Qdrant collection：knowledge_chunks_bge_m3_v1
Top-K：5
最大候选：20
Chunk 目标：500 tokens
Chunk 最大：700 tokens
Overlap：80 tokens
最低分：0.60
高置信分：0.625
最低证据覆盖：0.50
```

这些是当前项目的演示配置，不是生产认证参数。

---

# 第三部分：写入链路

## 1. 管理员上传文档

入口：

```text
POST /api/v1/admin/knowledge/documents
```

进入：

```text
KnowledgeDocumentService.create_document
```

做这些事：

```text
校验管理员权限
校验文件类型和大小
保存原始文件
创建文档记录
创建版本记录
触发 process_version
```

## 2. 解析

parser 支持：

```text
PDF
DOCX
Markdown
TXT
HTML
```

不支持 OCR。

扫描版 PDF 没有可提取文本，会失败。

## 3. 清洗和切块

清洗：

```text
去多余空白
保留段落和标题
保留页码和章节信息
```

切块：

```text
按结构优先
控制最大 token
保留 overlap
记录 chunk_index
记录 page_number 和 section_title
```

Chunk 写入 MySQL。

## 4. 向量化

调用：

```text
BgeM3EmbeddingProvider.embed_documents
```

生成 1024 维向量。

写入 Qdrant：

```text
chunk_id
vector
document_id
version_id
embedding_model
```

## 5. 数量校验

写完 Qdrant 后：

```text
Qdrant 当前版本的 point 数
必须等于
MySQL 当前版本的 chunk 数
```

不一致就失败。

这一步防止“MySQL 有正文，Qdrant 少向量”。

## 6. 发布

版本状态：

```text
UPLOADED
-> PROCESSING
-> INDEXED
-> PUBLISHED
```

旧发布版本变成：

```text
SUPERSEDED
```

只有 PUBLISHED 版本能被检索。

## 7. 更新和删除

更新文档：

```text
创建新版本
重新解析和索引
发布新版本
旧版本标记 SUPERSEDED
```

删除文档：

```text
删除 MySQL 文档和 Chunk
删除 Qdrant 对应版本向量
删除原始文件
```

---

# 第四部分：查询链路

## 1. Agent 路由

用户问题进入：

```text
classify_intent
-> RAG
-> retrieve_knowledge
```

RAG 路由只处理知识类问题。

订单、库存、售后记录仍然走 Tool。

## 2. 先查 ACL

```text
KnowledgeRetrievalService.retrieve_with_diagnostics
-> list_retrievable_versions(is_admin=user.is_admin)
```

只拿到当前用户可见的已发布版本。

普通用户只能拿 PUBLIC。

管理员可以拿 PUBLIC 和 ADMIN_ONLY。

## 3. 问题向量化

```text
BgeM3EmbeddingProvider.embed_query
```

生成 query 向量。

## 4. Qdrant 检索

只在这些 version_id 里召回：

```text
Qdrant search
filter version_id in 可见版本
limit 最大候选数
```

不把全库都召回后再过滤。

先限制范围，减少越权和无效候选。

## 5. MySQL 回查

拿到 chunk_id 后：

```text
KnowledgeChunkRepository.list_retrieval_rows
```

按 chunk_id 和权限再查一次。

Qdrant 有、MySQL 没有的 point 直接丢弃。

## 6. 构造 RetrievalItem

包含：

```text
chunk_id
document_id
version_id
document_title
content
score
page_number
section_title
original_filename
```

正文来自 MySQL。

分数来自 Qdrant。

## 7. 证据判断

进入：

```text
evaluate_rag_evidence
```

规则：

```text
没有结果 -> NO_RETRIEVAL / NO_ALLOWED_DOCUMENTS / NO_CANDIDATES
最高分 < 0.60 -> LOW_SCORE
0.60 <= 最高分 < 0.625 且词面覆盖 < 0.50 -> LOW_EVIDENCE
其他 -> ACCEPTED
```

这里的词面覆盖是中文 bigram 加字母数字词，不是另一个模型。

## 8. 回答或拒答

如果证据不足：

```text
retrieved_items 清空
knowledge_answer 返回固定拒答
```

如果证据足够：

```text
select_context
-> LLM 基于上下文回答
-> sources_from_items
-> validate_output 检查 source
```

来源必须来自已检索 Chunk。

模型不能自己编一个来源。

---

# 第五部分：完整代码链

## 1. 写入链

```text
管理员上传
-> knowledge API
-> KnowledgeDocumentService.create_document
-> 保存文件
-> 创建文档和版本
-> process_version
-> DocumentParser.parse
-> clean_documents
-> Chunker.chunk
-> KnowledgeChunkRepository.bulk_create
-> BgeM3EmbeddingProvider.embed_documents
-> QdrantVectorStore.upsert
-> count_by_version 校验
-> 版本 INDEXED
-> publish_version
-> 版本 PUBLISHED
```

## 2. 查询链

```text
用户问题
-> Agent classify_intent
-> route RAG
-> retrieve_knowledge_node
-> KnowledgeRetrievalService.retrieve_with_diagnostics
-> list_retrievable_versions
-> embed_query
-> QdrantVectorStore.search
-> list_retrieval_rows
-> 构造 RetrievalItem
-> evaluate_rag_evidence
-> knowledge_answer_node
-> select_context
-> LLM
-> sources_from_items
-> validate_output
```

## 3. 拒答链

```text
没有可见版本
或没有候选
或最高分低
或分数模糊且词面覆盖低
-> decision.answerable = False
-> retrieved_items = []
-> knowledge_answer_node 返回固定拒答
-> sources = []
```

---

# 第六部分：代码阅读顺序

## 第 1 步：先看检索

打开：

```text
backend/app/services/rag/retrieval_service.py
```

只看：

```text
retrieve
retrieve_with_diagnostics
```

重点看五个动作：

```text
限制 top_k
查可见版本
Qdrant 按版本过滤
MySQL 回查
丢弃 stale point
```

## 第 2 步：看证据判断

打开：

```text
agent/rag_evidence.py
```

只看：

```text
evaluate_rag_evidence
evidence_coverage
_query_terms
```

要能说出：

```text
空结果拒答
低分拒答
模糊分数看词面覆盖
高置信直接接受
```

## 第 3 步：看 Agent 节点

打开：

```text
agent/nodes.py
```

只看：

```text
retrieve_knowledge_node
knowledge_answer_node
```

重点：

```text
证据不足时清空 retrieved_items
回答节点只使用通过判断的片段
```

## 第 4 步：看写入

打开：

```text
backend/app/services/rag/document_service.py
```

只看：

```text
create_document
create_version
process_version
publish_version
delete_document
```

要能说出：

```text
版本不可变
发布旧版本被 SUPERSEDED
MySQL chunk 和 Qdrant 数量校验
```

## 第 5 步：看解析和切块

打开：

```text
parser.py
text_cleaner.py
chunker.py
```

只看：

```text
支持哪些格式
怎么清洗
chunk 最大长度和 overlap
```

不需要背 PDF 解析库的内部实现。

## 第 6 步：看向量

打开：

```text
embedding.py
```

只看：

```text
embed_documents
embed_query
维度校验
模型懒加载
```

不需要背 BGE-M3 的网络结构。

## 第 7 步：看测试和评测

测试：

```text
backend/tests/services/test_rag_components.py
backend/tests/services/test_rag_pdf.py
agent/tests/test_rag_evidence.py
```

评测：

```text
backend/scripts/task0212_rag_eval.py
```

测试看边界。

评测看当前策略在数据集上的表现。

---

# 第七部分：代码怎么读才不容易忘

## 方法一：先画两条线

写入线：

```text
文档 -> 解析 -> 切块 -> 向量 -> MySQL + Qdrant
```

查询线：

```text
问题 -> ACL -> 向量 -> 回查 -> 证据 -> 回答/拒答
```

画不出来，就不要继续看细节。

## 方法二：只追一个 Chunk

选一个 PDF。

从上传开始追：

```text
文件怎么存
解析出几段
切出几个 chunk
每个 chunk 的 MySQL 行
Qdrant point 的 payload
```

再问一个问题，追这个 chunk 怎么被召回。

## 方法三：只看失败场景

```text
没有可见文档
Qdrant 没有候选
Qdrant 有但 MySQL 没有
分数低于 0.60
分数模糊且覆盖低
文档解析失败
Qdrant 写入数量不一致
```

能解释这些失败，比背成功路径更有用。

## 方法四：看评测而不是只看代码

评测会告诉你：

```text
哪些问题被接受
哪些问题被拒绝
拒绝原因是什么
最高分是多少
证据覆盖是多少
```

这比“感觉效果不错”可靠。

---

# 第八部分：面试怎么讲

## 30 秒版

RAG 分写入和查询两条链路。

写入时，文档解析、清洗、切块，正文写 MySQL，向量写 Qdrant。

查询时，先查 MySQL 当前用户可见的版本，再用 Qdrant 按 version_id 过滤召回，召回后回 MySQL 取正文和权限，最后根据分数和证据覆盖决定回答还是拒答。

Qdrant 只负责召回，MySQL 才是正文、版本和权限的权威源。

## 1 分钟版

这个项目的 RAG 不是简单把文档丢给向量库。

写入时，管理员上传文档，系统解析、清洗、切块，Chunk 正文写 MySQL，BGE-M3 向量写 Qdrant，并且校验两边数量一致，再发布版本。

查询时，先用 MySQL 查当前用户可访问的已发布版本，只把这些 version_id 传给 Qdrant 做过滤召回。召回后拿 chunk_id 回 MySQL 再查正文和权限，Qdrant 里过期或越权的 point 会被丢弃。

最后做证据判断：没有结果、最高分低于阈值，或者分数模糊且词面覆盖不足，就直接拒答；只有证据足够才让模型回答，来源由后端从检索片段构造。

---

# 第九部分：RAG 效果怎么样

## 1. 我实际跑的评测

脚本：

```text
backend/scripts/task0212_rag_eval.py
```

数据集：

```text
42 条有效问题
30 条可回答
12 条无答案
```

结果：

```text
可回答问题接受率：30/30 = 100%
无答案问题拒绝率：12/12 = 100%
误拒：0
ACL 普通用户过滤：1/1
ACL 管理员可见：1/1
```

原因分布：

```text
ACCEPTED：30
LOW_SCORE：9
LOW_EVIDENCE：3
```

分数分布：

```text
可回答问题 Top1 中位数：0.674
无答案问题 Top1 中位数：0.489
可回答问题最低分：0.604
无答案问题最高分：0.620
```

说明：

```text
可回答和无答案的分数有明显间隔；
边界区间主要靠词面证据兜底；
低分拒答是主要拒答原因。
```

## 2. 这个结果怎么解读

好消息：

```text
无答案策略有效
ACL 预过滤有效
低分和低证据能拒答
回答来源来自检索片段
```

但不能说“RAG 准确率 100%”。

原因：

```text
数据集是合成的
只有 6 篇文档
问题只有 42 条
阈值是在这组数据上调的
评测主要看接受/拒绝，不是完整答案质量
ACL 样本各只有 1 条
没有真实用户分布
没有大规模 Qdrant/MySQL 压测
```

## 3. 我的评价

作为面试 Demo：

```text
7.5 / 10
```

优点是链路完整：

```text
写入
权限
召回
回查
拒答
来源
版本
测试
```

作为生产系统：

```text
4 / 10
```

短板是：

```text
没有 Reranker
没有混合检索
没有 OCR
没有大规模评测
没有人工答案质量评估
没有多租户
没有异步索引和任务队列
```

面试时可以说：

> 这组 42 条小样本评测上，可回答接受率和无答案拒绝率都是 100%，但它只能说明策略在这个合成集上有效，不能证明生产准确率。

这句话比“我的 RAG 准确率 100%”可信得多。

## 4. 当前测试情况

RAG 相关测试：

```text
17 passed
```

覆盖：

```text
解析
清洗
切块
PDF 中文和多页
证据判断
分数边界
ACL 无答案策略
```

全量后端测试之前是：

```text
336 passed
```

---

# 第十部分：高频面试题

## 1. RAG 是什么

先检索资料，再让模型基于资料回答。

## 2. RAG 和微调的区别

RAG 不改模型参数，知识更新快，能返回来源。

微调改模型参数，成本和更新成本更高。

## 3. 为什么用 Qdrant 和 MySQL 两个存储

Qdrant 负责向量相似度召回。

MySQL 负责正文、版本、权限和发布状态。

Qdrant 不是权威源。

## 4. 为什么召回后还要查 MySQL

Qdrant 可能过期，文档可能删除或换版本。

MySQL 回查保证正文和权限最新。

## 5. 怎么防止越权检索

先查 MySQL 可见版本，只把这些 version_id 传给 Qdrant 过滤。

召回后再回 MySQL 校验一次。

## 6. 文档怎么切块

结构优先，控制最大 token，保留 overlap，记录页码和章节。

当前目标 500，最大 700，overlap 80。

## 7. 为什么用 BGE-M3

中文和多语言检索效果较好，当前项目使用 1024 维向量。

## 8. 怎么防止模型乱答

没有结果、低分、低证据覆盖时直接拒答。

只有证据足够才调用模型回答。

## 9. 阈值怎么定

当前是离线校准的演示参数：

```text
0.60 最低分
0.625 高置信分
0.50 最低证据覆盖
```

不是生产认证值。

## 10. 文档更新怎么处理

创建新版本，重新索引，发布新版本。

旧版本标记 SUPERSEDED。

## 11. 删除文档怎么清理

删除 MySQL 文档、版本和 Chunk。

删除 Qdrant 对应版本向量。

删除原始文件。

## 12. RAG 和 Agent Tool 的区别

RAG 查知识。

Tool 查实时业务数据或生成待确认操作。

## 13. 怎么评估 RAG

看检索命中、答案质量、无答案拒绝率、误拒率、延迟和权限隔离。

当前项目做了小样本离线评测。

## 14. 当前 RAG 的缺点

没有 Reranker、混合检索、OCR、大规模评测和生产级异步索引。

## 15. 如果继续优化会做什么

```text
加 Reranker
加 BM25/向量混合检索
扩大评测集
做人工答案评分
加 OCR
异步索引和任务队列
加检索延迟和失败监控
```

---

# 第十一部分：最容易答错的点

错误一：说 Qdrant 是知识库权威源。

正确：MySQL 才是正文、版本和权限权威源。

错误二：说向量相似度高就一定回答。

正确：还要过分数阈值和证据覆盖。

错误三：说 ACL 在 Qdrant 里做一次就够。

正确：先过滤，召回后还要回 MySQL 校验。

错误四：说 RAG 准确率 100%。

正确：只是小样本合成评测上接受/拒绝全对，不能代表生产。

错误五：说 RAG 可以代替订单工具。

正确：RAG 查知识，订单和库存走 Tool。

---

# 第十二部分：五分钟自检

1. RAG 的写入链路是什么？

2. RAG 的查询链路是什么？

3. 为什么 MySQL 和 Qdrant 都要用？

4. 怎么防止越权检索？

5. 为什么召回后还要回查？

6. 什么情况下拒答？

7. 当前阈值是多少？

8. 文档更新和删除怎么处理？

9. 当前 RAG 的效果怎么评估？

10. 当前 RAG 最大的三个缺点是什么？

---

# 第十三部分：最后背这一句

RAG 写入时把文档解析、切块、向量化，正文和权限写 MySQL，向量写 Qdrant；查询时先按 MySQL 可见版本过滤，再让 Qdrant 召回，召回后回 MySQL 校验正文和权限，最后按分数和证据覆盖决定回答还是拒答；小样本评测表现不错，但它是演示级，不是生产级准确率。
