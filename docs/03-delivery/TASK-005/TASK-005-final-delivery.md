# TASK-005 RAG 知识库最终交付记录

> 状态：代码实现与自动化验收完成，待人工验收
> 更新日期：2026-11-15
> 代码分支：`feature/task-004-order`
> 设计依据：`docs/02-design/TASK-005-RAG-详细设计.md`

## 1. 最终结论

```text
TASK-005：RAG 知识库代码实现与自动化验收完成，待人工验收。
```

已完成文档管理、版本发布、文件解析、Chunk、BGE-M3 Embedding、Qdrant 索引、Retrieval、权限过滤、版本过滤、MySQL 二次校验、删除和重试。

未开始 TASK-006。

## 2. 实现范围

### MySQL 权威数据

- `knowledge_documents`
- `knowledge_document_versions`
- `knowledge_chunks`

MySQL 保存文档、版本和 Chunk 正文；Qdrant 只保存向量和关联 ID。

### 文档能力

- 管理员上传文档；
- 文档列表和详情；
- 新版本上传；
- 版本发布；
- 失败版本重试；
- 逻辑删除；
- 文档版本状态流转；
- 原始文件本地存储。

### 处理能力

- PDF、DOCX、Markdown、TXT、HTML 解析；
- 文本清洗；
- 结构优先的 Chunk 切分；
- BGE-M3 批量 Embedding；
- Qdrant 写入、删除和检索；
- MySQL Chunk 数与 Qdrant Point 数一致性校验；
- 索引失败标记和重试。

### 检索能力

- Dense Vector Search；
- 当前发布版本过滤；
- PUBLIC / ADMIN_ONLY 权限过滤；
- MySQL 二次校验；
- 来源、页码、章节和文件名返回；
- Top-K 限制；
- Qdrant 陈旧 Chunk 丢弃。

### API

```text
POST   /api/v1/knowledge/documents
GET    /api/v1/knowledge/documents
GET    /api/v1/knowledge/documents/{document_id}
POST   /api/v1/knowledge/documents/{document_id}/versions
GET    /api/v1/knowledge/documents/{document_id}/versions/{version_id}
POST   /api/v1/knowledge/documents/{document_id}/versions/{version_id}/publish
POST   /api/v1/knowledge/documents/{document_id}/versions/{version_id}/retry
DELETE /api/v1/knowledge/documents/{document_id}
POST   /api/v1/knowledge/retrieve
```

### 运维命令

```bash
python -m app.rag_cli check
python -m app.rag_cli retry-failed
python -m app.rag_cli pending
```

不引入 Celery、RabbitMQ、Kafka 或微服务。

## 3. 数据库迁移

迁移：

```text
b96d3aae8b3d  add knowledge documents versions chunks
```

已执行：

- upgrade；
- downgrade 到 `5f14d68fcbd1`；
- 再次 upgrade；
- `alembic check`。

结果：

```text
No new upgrade operations detected.
```

## 3.1 依赖锁文件与干净环境

已根据 `requirements.in` / `requirements-dev.in` 使用 `uv pip compile` 重新生成：

```text
requirements.txt
requirements-dev.txt
```

Python 3.12 兼容版本：

```text
torch==2.15.0+cpu
sentence-transformers==6.3.0
qdrant-client==1.20.0
pypdf==7.1.0
python-docx==1.2.0
beautifulsoup4==4.15.0
python-multipart==0.0.33
```

CPU 版本通过以下索引解析，避免 Docker 构建拉取 CUDA/NVIDIA wheel：

```text
--extra-index-url https://download.pytorch.org/whl/cpu
--index-strategy unsafe-best-match
```

干净环境验证：

```text
独立 Python 3.12.10 venv
uv pip install --require-hashes -r requirements.txt
uv pip install --require-hashes -r requirements-dev.txt
成功
```

Dockerfile 已使用相同的 CPU 索引安装锁文件。

## 4. BGE-M3 与 Qdrant 实际验证

### BGE-M3

环境：

```text
Python 3.12.10
torch 2.15.0+cpu
sentence-transformers 6.3.0
设备：CPU
```

首次加载：

```text
BAAI/bge-m3
加载约 352 秒
输出维度 1024
向量 L2 norm = 1.0
```

说明：

- 未使用 GPU；
- 首次加载包含模型下载/缓存初始化；
- 后续使用本地缓存；
- 模型缓存目录为项目 `.cache/huggingface`，已加入 `.gitignore`。

### Qdrant

```text
容器：ecommerce-qdrant
镜像：qdrant/qdrant:v1.20.1
地址：http://127.0.0.1:6333
health：200
Collection：knowledge_chunks_bge_m3_v1
Vector：1024，Cosine
```

已验证：

- Collection 创建；
- Payload Index 创建；
- Point upsert；
- Point count；
- 向量检索；
- 按 version 删除；
- 按 document 删除；
- 服务健康检查。

## 5. 实际 API 链路验证

使用真实 BGE-M3 + 真实 Qdrant，通过 FastAPI ASGI 接口执行：

```text
上传 Markdown 文档 → 解析 → Chunk → BGE-M3 → Qdrant → 发布 → 检索 → 删除
```

实际结果：

```text
UPLOAD   201
PUBLISH  200
RETRIEVE 200
  返回 1 条
  score = 0.8600424
  content = 签收后 7 天内可以申请退货退款。
DELETE   204
删除后检索不再返回该文档
```

未使用 Mock Embedding 或 Mock Qdrant 替代该次验证。

## 6. 自动化测试

新增测试：

```text
tests/services/test_rag_components.py
tests/integration/test_knowledge_api.py
```

覆盖：

- TXT/Markdown/HTML/DOCX 解析；
- PDF 正常文本、多页、中文、空白页、损坏文件；
- 非法格式、空文件、错误 PDF 签名；
- 文本清洗；
- Chunk 最大长度、序号和章节元数据；
- 文档上传；
- 普通用户上传拒绝；
- PUBLIC / ADMIN_ONLY 权限；
- 文档详情越权；
- 版本上传；
- 旧版本不可检索；
- 新版本发布后切换；
- 失败版本重试；
- 删除后不可检索；
- Qdrant 返回不存在 Chunk 的 MySQL 二次校验；
- 文档/版本删除清理。

实际测试：

```text
pytest: 276 passed
```

说明：

- 测试使用测试 MySQL；
- RAG 单元/API 测试使用可控的 Fake Embedding/Fake Vector Store，避免每次测试加载大模型；
- 真实 BGE-M3 和真实 Qdrant 另做了独立 smoke 验证。

### 6.1 PDF 测试

新增：

```text
tests/services/test_rag_pdf.py
```

使用 ReportLab 生成真实 PDF，覆盖：

- 中文正常文本；
- 多页 PDF 和页码；
- 空白页/无有效文本；
- 损坏 PDF。

实际结果：

```text
3 passed
```

### 6.2 RAG 评测数据集

数据文件：

```text
tests/evaluation/rag_eval_dataset.json
tests/evaluation/knowledge/refund.md
tests/evaluation/knowledge/return.md
tests/evaluation/knowledge/exchange.md
tests/evaluation/knowledge/shipping.md
tests/evaluation/knowledge/product.md
```

规模：

```text
5 个知识领域
25 条人工标注问题
```

执行脚本：

```text
scripts/evaluate_rag.py
```

结果文件：

```text
docs/03-delivery/TASK-005/rag-evaluation-results.json
```

真实 BGE-M3 + Qdrant 指标：

```text
Recall@5:            1.0
MRR:                 1.0
Precision@5:         0.2
Empty Retrieval Rate: 0.0
```

说明：

- Recall@5 达到设计目标 `>= 0.85`；
- Precision@5 为 0.2，是因为每条问题只标注一个目标文档，Top-5 中其余文档按文档级相关性视为不相关；
- 未修改测试数据迎合指标；
- 数据集和脚本可重复执行。

## 6.3 Docker 构建与启动

Qdrant 固定版本：

```text
qdrant/qdrant:v1.20.1
```

应用镜像构建：

```text
docker compose build app
Image e-ecommerce-agent-app Built
Image ID: 202fd2b3b927
Image size: 2.24GB
```

缓存构建复核：

```text
docker compose build --quiet app
exit 0
```

应用启动：

```text
docker compose up -d --no-deps app
app container: Up
GET /api/v1/health/live  -> 200 {"status":"ok"}
GET /api/v1/health/ready -> 200 {"status":"ok","checks":{"database":"ok","redis":"ok"}}
```

容器状态：

```text
mysql   healthy
redis   healthy
qdrant  qdrant/qdrant:v1.20.1
app     Up
```

从 App 容器内连接 Qdrant：

```text
settings.rag_qdrant_url = http://qdrant:6333
Qdrant health_check = True
```

实际 Qdrant 版本：

```text
qdrant/qdrant:v1.20.1
version 1.20.1
```

### 6.4 模型加载与同步处理

API 路径使用 `app/services/rag/runtime.py` 的进程级单例：

```text
get_embedding_provider()
get_chunker()
get_vector_store()
```

`_document_service()` 和 Retrieval Service 都注入同一个实例，因此不会在每个请求重复加载 BGE-M3 或重复创建 Qdrant 客户端；模型只在首次使用时懒加载一次。

当前仍为同步处理：

- 上传请求内完成解析、Chunk、Embedding 和 Qdrant 写入；
- 不引入 Celery/MQ/独立 Worker；
- 大文件会占用请求时间；
- 失败版本可通过 API 或 CLI 重试。

## 7. 代码质量

实际执行：

```text
ruff check app tests: All checks passed
mypy app: Success: no issues found in 104 source files
```

说明：

- `mypy app tests` 仍会受到既有测试代码的类型问题影响；
- 本次新增的 `app` 代码 Mypy 通过；
- 未格式化或修改 TASK-001～004 业务实现。

## 8. 修改文件

新增：

```text
alembic/versions/b96d3aae8b3d_add_knowledge_documents_versions_chunks.py
app/api/v1/knowledge.py
app/infrastructure/__init__.py
app/infrastructure/storage/__init__.py
app/infrastructure/storage/base.py
app/infrastructure/storage/local.py
app/infrastructure/vector/__init__.py
app/infrastructure/vector/qdrant.py
app/models/knowledge_chunk.py
app/models/knowledge_document.py
app/models/knowledge_document_version.py
app/repositories/knowledge.py
app/schemas/knowledge.py
app/services/rag/__init__.py
app/services/rag/chunker.py
app/services/rag/document_service.py
app/services/rag/embedding.py
app/services/rag/parser.py
app/services/rag/retrieval_service.py
app/services/rag/runtime.py
app/services/rag/text_cleaner.py
app/rag_cli.py
tests/integration/test_knowledge_api.py
tests/services/test_rag_components.py
tests/services/test_rag_pdf.py
scripts/evaluate_rag.py
tests/evaluation/rag_eval_dataset.json
tests/evaluation/knowledge/
docs/03-delivery/TASK-005/rag-evaluation-results.json
```

修改：

```text
app/api/router.py
app/core/config.py
app/models/__init__.py
requirements.in
requirements.txt
requirements-dev.in
requirements-dev.txt
Dockerfile
.env.example
.gitignore
docker-compose.yml
tests/test_migrations.py
```

## 9. 遗留问题与环境限制

1. 文档处理当前在请求流程内同步执行，没有引入独立后台 worker。
   - 符合“不引入 MQ/Celery”的边界；
   - 失败版本可通过 API 或 CLI 重试；
   - 生产大文件建议后续改用受控后台任务。
2. 当前测试中的 RAG 权限/版本测试使用 Fake Embedding/Fake Qdrant；真实 BGE-M3/Qdrant 通过独立 smoke 和评测脚本验证。
3. `mypy app tests` 仍会受到既有测试代码的类型问题影响；`mypy app` 通过。
4. Docker 镜像已构建并启动验证，但本轮未做生产服务器部署。
5. 未 commit、未 push。

## 10. 当前 Git 状态

```text
分支: feature/task-004-order
HEAD: de3e9ad
```

未执行：

- commit；
- push；
- TASK-006；
- 数据库结构之外的 TASK-001～004 业务修改。

由人工验收后再决定是否提交。
