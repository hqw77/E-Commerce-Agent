# E-Commerce Agent 项目总进度

> 更新日期：2026-11-16
> 当前分支：`feature/task-004-order`
> 用途：记录 TASK-001～018 的阶段状态和下一任务，不替代各任务设计/交付文档。

## 1. 当前阶段结论

```text
TASK-004：业务代码开发与自动化验收完成，支付宝沙箱真实 E2E 延期。
TASK-005：RAG 知识库代码实现与自动化验收完成，待人工验收。
TASK-006：LangGraph Agent 核心代码实现与自动化验收完成，待人工验收。
TASK-007：Agent 业务工具集成代码实现与自动化验收完成，待人工验收。
TASK-008～013：React 管理后台代码实现、构建与前端验收完成，待人工验收。
TASK-014：前后端联调代码实现与自动化验收完成，待人工验收。
TASK-015：自动化实现完成；真实支付宝沙箱和部分 AI 评估未验证。
TASK-016：本地生产化 Docker Compose 完成，真实支付/HTTPS 未验证。
```

## 1.1 总体设计基线

- [V1.2 项目总体规划](02-design/V1.2-项目总体规划.md)
- [系统总体架构](02-design/系统总体架构.md)
- [AI Agent 总体设计](02-design/AI-Agent-总体设计.md)
- [AI Agent 安全设计基线](architecture.md)
- [TASK-005 最终交付记录](03-delivery/TASK-005/TASK-005-final-delivery.md)

说明：

- 三份总体设计是 V1.2 的设计入口；
- 安全基线已完成本轮 P0 修正，仍需 Review 后才能冻结；
- TASK-005 已实现，等待人工验收；
- TASK-006 已实现，等待人工验收；
- TASK-007 已实现，等待人工验收；
- TASK-008～013 已实现，等待人工验收；
- TASK-014 已实现，等待人工验收；
- TASK-015 已实现，存在未验证项；

支付宝沙箱 E2E 延期事项：

- 支付宝沙箱真实支付 E2E；
- 支付宝沙箱真实退款 E2E；
- 支付宝异步通知真实联调；
- 支付宝退款查询真实全链路验证。

以上事项统一在 **TASK-015（E2E 测试与最终评测）** 重新安排。

未执行的沙箱测试不得描述为通过。

---

## 2. TASK 状态

| TASK | 内容 | 状态 | 说明 |
|---|---|---|---|
| TASK-001 | 基础设施 | 已完成 | 配置、数据库、Redis、日志、异常、健康检查 |
| TASK-002 | 用户认证 | 已完成 | 注册、登录、Refresh、Token、权限依赖 |
| TASK-003 | 商品与库存 | 已完成 | 分类、商品、SKU、库存、流水 |
| TASK-004 | 订单、支付与售后 | 业务代码与自动化验收完成；沙箱 E2E 延期 | 267 个测试通过；Ruff/Mypy/Alembic 通过 |
| TASK-005 | RAG 知识库 | **代码实现与自动化验收完成，待人工验收** | 276 tests passed；BGE-M3/Qdrant 已实跑 |
| TASK-006 | LangGraph Agent 核心 | **代码实现与自动化验收完成，待人工验收** | 317 tests passed；Agent API、LangGraph、Redis、Docker 已验证 |
| TASK-007 | Agent 与电商业务集成 | **代码实现与自动化验收完成，待人工验收** | 331 tests passed；Tool Registry、Prepare/Confirm、MySQL/Redis 已验证 |
| TASK-008～013 | React 管理后台 | **代码实现、构建与前端验收完成，待人工验收** | 6 frontend tests；TypeScript/ESLint/Vite Build；真实 API + Playwright UI smoke |
| TASK-014 | 前后端集成 | **代码实现与自动化验收完成，待人工验收** | 331 backend tests；7 Playwright E2E；真实 RAG/Agent Confirm |
| TASK-015 | E2E 测试与最终评测 | **自动化实现完成；真实沙箱/部分 AI 评估未验证** | 336 tests；7 Playwright；RAG/Agent 评估报告 |
| TASK-016 | Docker 生产部署 | **本地生产化验收完成；真实支付/HTTPS 未验证** | 生产 Compose、Nginx、迁移、持久化已验证 |
| TASK-017 | 云服务器与域名 HTTPS | 未开始 | 生产部署前必须复查支付渠道真实联调状态 |
| TASK-018 | 部署验证与项目交付 | 未开始 | 保持原顺序 |

---

## 3. TASK-004 最终状态

### 已完成

- 订单创建、查询、取消；
- 库存预占、释放、支付扣减、退货入库、换货出库；
- 支付单创建、MOCK 支付成功/失败；
- 支付宝 RSA2 适配器；
- 支付宝支付参数生成、支付查询、支付关闭；
- 支付宝全额退款真实网络调用；
- 退款查询、稳定 `out_request_no`、未知结果处理；
- 退款额度、状态和幂等；
- 售后三类流程与退款联动；
- 订单履约管理端接口；
- 自动化测试 `267 passed`；
- Ruff、Mypy、Alembic check 通过。

### 尚未验证

- 支付宝沙箱真实支付；
- 支付宝沙箱真实退款；
- 支付宝异步通知真实联调；
- 支付宝退款查询真实全链路。

这些属于 **TASK-015 延期验证项**，不是当前代码开发的阻塞项。

详细记录：

- [TASK-004 最终交付记录](03-delivery/TASK-004/TASK-004-final-delivery.md)
- [TASK-004 支付宝沙箱 E2E 清单](03-delivery/TASK-004/alipay-sandbox-e2e.md)

---

## 4. TASK-005 当前状态

已完成：

- 文档、版本、Chunk 的 MySQL 模型与迁移；
- 本地文件存储；
- PDF/DOCX/Markdown/TXT/HTML 解析；
- 文本清洗和结构优先 Chunk；
- BGE-M3 Embedding；
- Qdrant 向量写入、检索和删除；
- 文档 ACL、版本过滤、MySQL 二次校验；
- 文档上传、列表、详情、版本、发布、重试、删除 API；
- 自动化测试和真实 API smoke；
- RAG 运维 CLI。

当前环境限制：

- `requirements.txt` / `requirements-dev.txt` 已重新生成并在独立 3.12 环境验证；
- 文档处理当前在请求内同步执行，未引入后台 worker；
- PDF 正常文本、多页、中文、空白页和损坏文件测试已补齐；
- RAG Evaluation Dataset 已建立，Recall@5 = 1.0、MRR = 1.0；
- Docker 镜像已构建并启动验证，App 连接 Qdrant 正常；本轮未做生产服务器部署。

详细记录：

- [TASK-005 最终交付记录](03-delivery/TASK-005/TASK-005-final-delivery.md)

---

## 4.1 TASK-006 当前状态

已完成：

- LangGraph 1.2.22 RuntimeContext 注入与进程级 Graph 编译；
- DeepSeek `ChatOpenAI` Provider，实际使用 `max_tokens` 参数；
- Agent State 与 Graph 节点：会话加载、意图分类、普通回答、RAG 检索、知识回答、未开放操作、输出校验、会话保存；
- TASK-005 `KnowledgeRetrievalService` 集成，复用 Embedding/Qdrant 单例；
- Redis 会话历史、用户级限流、token 分布式锁、Lua 比较 token 后原子保存；
- 输入/输出 Guardrails、上下文预算、超时取消和来源校验；
- `POST /api/v1/agent/chat` Agent API；
- Agent 单元、Graph、Redis、API 和安全测试。

当前结果：

- 全量测试 `317 passed`；
- Ruff、Mypy、Alembic check 通过；
- Docker 镜像构建并启动，健康检查通过；
- 真实 DeepSeek 通用对话和知识回答 smoke 已执行成功；
- 未新增数据库迁移；
- TASK-007 尚未开始。

详细设计：

- [TASK-006 LangGraph Agent 核心设计](02-design/TASK-006-LangGraph-Agent-核心设计.md)

---

## 4.2 TASK-007 当前状态

已完成：

- Tool Registry、Pydantic Tool Schema、Tool Executor 和白名单；
- 商品搜索/详情、SKU、库存、订单、售后只读 Tool；
- 订单取消与售后申请 Prepare Tool；
- Redis action confirmation、nonce、参数哈希、TTL、Lua 原子消费；
- 独立认证 Confirm API，重新调用 OrderService / AfterSaleService；
- LangGraph Tool Calling 节点和最多工具次数限制；
- 真实 MySQL/Redis 订单取消、库存释放、售后申请和并发确认测试。

当前结果：

- 全量测试 `331 passed`；
- Ruff、Mypy、Alembic check 通过；
- Docker 镜像构建、启动和健康检查通过；
- 未新增数据库迁移；
- TASK-008 尚未开始。

详细设计：

- [TASK-007 Agent 业务工具集成设计](02-design/TASK-007-Agent-业务工具集成设计.md)

---

## 4.3 TASK-008～013 当前状态

已完成：

- 独立 `frontend/` React + TypeScript + Vite 工程；
- 登录、注册、Token Refresh 协调、登出和受保护路由；
- 管理后台布局、导航和面包屑；
- 商品、SKU、库存和库存流水页面；
- 订单、售后页面和支付状态只读展示；
- RAG 文档列表、上传、详情、删除和检索测试；
- AI Agent 对话、RAG 来源、Pending Action 和 Confirm 交互；
- 统一 Axios 客户端、TypeScript 类型和 TanStack Query 数据层；
- 真实 FastAPI API smoke、Playwright UI smoke 和前端单元测试。

当前结果：

- 前端 6 tests passed；
- TypeScript、ESLint、Vite Build 通过；
- 真实 API：登录、`/me`、知识库列表、管理员商品/订单/售后/支付列表、商品/SKU/库存操作已验证；
- 真实 DeepSeek Agent：普通对话、订单 Tool、取消 Prepare、Confirm 和订单 `CANCELLED` 已验证；
- UI：登录、Dashboard、商品列表、商品详情、库存、Agent 对话/Tool/Prepare/Confirm、路由保护、Token Refresh、登出已验证；
- 本地 `.env` 已配置 DeepSeek Key，未进入 Git；
- 未修改 TASK-001～007 后端业务规则；
- TASK-014 已实现，等待人工验收；
- TASK-015 已实现，存在未验证项；

详细设计和交付报告：

- [TASK-008～013 前端整体设计](02-design/TASK-008-013-前端整体设计.md.md)
- [TASK-008～013 前端阶段交付报告](03-delivery/TASK-008-013/TASK-008-013-前端阶段交付报告.md)

## 4.4 TASK-014 当前状态

已完成：

- 65 个 API 的契约矩阵和测试数据方案；
- 分类管理列表、创建、编辑页面；
- 知识库发布、重试、上传新版本 UI；
- Playwright E2E 框架和随机测试数据工具；
- 真实 API 认证、权限、商品、SKU、库存、订单、售后联调；
- 真实 RAG 上传、INDEXED、PUBLISHED 和非空检索；
- Agent Chat、Tool、Prepare、Confirm 完整闭环；
- OpenAPI 路径、请求/响应和业务规则保持不变。

当前结果：

- Backend `331 passed`；
- Ruff、Mypy、Alembic check 通过；
- Frontend typecheck/lint/Vitest/build 通过；
- Playwright `7 passed`；
- Docker 开发栈 app/mysql/redis/qdrant 运行正常；
- 未新增 migration；
- TASK-015 已实现，存在未验证项；

详细报告：

- [TASK-014 最终验收报告](03-delivery/TASK-014/TASK-014-最终验收报告.md)
- [TASK-014 API 契约矩阵](03-delivery/TASK-014/TASK-014-API契约矩阵.md)
- [TASK-014 测试数据方案](03-delivery/TASK-014/TASK-014-测试数据方案.md)

## 4.5 TASK-015 当前状态

已完成：

- TASK-015 测试计划、数据清理、支付/RAG/Agent 方案；
- 5 个新增安全/支付安全测试；
- TASK-015 RAG 数据集（33 问题，含 8 个无答案）；
- RAG 真实 BGE-M3/Qdrant 评估；
- Agent 30 条评估用例和 10 条真实 DeepSeek 抽样；
- 分类创建、知识库新版本上传 Playwright 断言；
- 全量 336 tests、7 Playwright E2E、前端检查。

未验证/未通过：

- 真实支付宝沙箱支付、通知、退款、退款查询（无凭证，SKIPPED）；
- RAG No-answer Accuracy = 0，检索会返回相似文档；
- RAG 精确 Chunk Recall 和 ACL 数据集未覆盖；
- Agent 真实模型仅 10/30 抽样；Token 用量接口不返回；
- 真实模型完整 Tool Call 审计不可得。

详细报告：

- [TASK-015 测试计划](04-testing/TASK-015/TASK-015-测试计划.md)
- [TASK-015 安全测试报告](04-testing/TASK-015/TASK-015-安全测试报告.md)
- [TASK-015 支付测试报告](04-testing/TASK-015/TASK-015-支付测试报告.md)
- [TASK-015 RAG 评估报告](04-testing/TASK-015/TASK-015-RAG评估报告.md)
- [TASK-015 Agent 评估报告](04-testing/TASK-015/TASK-015-Agent评估报告.md)

## 4.6 TASK-016 当前状态

已完成：

- 独立 `docker-compose.prod.yml`；
- 前端多阶段 Dockerfile + Nginx；
- 独立 production Volume；
- 显式 `migrate` 服务；
- edge/data 网络隔离；
- MySQL 专用用户；
- 上传文件和 BGE-M3 模型缓存持久化；
- 生产 E2E 7 passed；
- 336 backend tests、6 frontend tests。

未验证/未做：

- 真实支付宝沙箱；
- HTTPS/域名/云服务器（TASK-017）；
- 备份恢复（TASK-018）；
- Nginx master 进程仍为 root（Backend 非 root）；
- `model_cache_prod` 是 external volume，新环境需先初始化。

报告：

- [TASK-016 最终验收报告](03-delivery/TASK-016/TASK-016-最终验收报告.md)
- [生产部署说明](../deploy/docker/README.md)

---

## 5. TASK-015 预留验收要求

TASK-015 必须纳入：

1. 支付宝沙箱真实支付 E2E；
2. 支付宝沙箱真实退款 E2E；
3. 支付宝异步通知真实联调；
4. 支付宝退款查询真实全链路验证；
5. 真实联调只使用沙箱，不使用真实资金；
6. 密钥只从环境变量或安全配置读取，不进入 Git；
7. 回调 URL、签名、金额、订单号、幂等和本地状态必须有确定性断言；
8. 不得用 MOCK 或静态检查代替真实沙箱联调；
9. 未执行项必须明确标记为未验证；
10. RAG 权限、版本和删除场景纳入安全测试。

---

## 6. TASK-017 生产部署前检查

TASK-017 正式生产部署前必须重新检查：

- 支付渠道真实联调状态；
- 支付宝生产应用配置和密钥管理；
- 异步通知公网 HTTPS 地址；
- 支付/退款查询和关闭能力；
- 沙箱与生产配置差异；
- 生产环境是否仍禁用 MOCK 支付；
- 支付失败、未知退款和人工处理流程；
- RAG Qdrant、模型缓存和依赖锁文件。

TASK-004 的沙箱延期不改变 TASK-017 的部署前检查责任。

---

## 7. 边界

- 保持 TASK-001～018 编号、顺序和总体规划不变；
- 不新增顶层 TASK；
- TASK-007～016 已完成，不启动 TASK-017；
- 不修改已完成的 TASK-001～004 业务逻辑；
- 不执行未经授权的 Git commit 或 push。
