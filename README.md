# E-Commerce Agent

基于 Python 3.12、FastAPI 和大语言模型技术构建的电商 AI Agent 工程实践项目。目标是把真实电商业务系统与 RAG 知识检索、LangGraph Agent、Tool Calling 和安全控制结合起来，形成一个可运行、可测试、可解释的应用。

## 当前进度

| TASK | 内容 | 状态 |
|---|---|---|
| TASK-001 | 基础设施 | 已完成 |
| TASK-002 | 用户认证 | 已完成 |
| TASK-003 | 商品与库存 | 已完成 |
| TASK-004 | 订单、支付与售后 | 业务代码与自动化验收完成；支付宝沙箱真实 E2E 延期至 TASK-015 |
| TASK-005 | RAG 知识库 | 代码实现与自动化验收完成，待人工验收 |
| TASK-006 | LangGraph Agent 核心 | 代码实现与自动化验收完成，待人工验收 |
| TASK-007 | Agent 与电商业务工具集成 | 代码实现与自动化验收完成，待人工验收 |
| TASK-008～013 | React 管理后台 | 代码实现、构建与前端验收完成，待人工验收 |
| TASK-014 | 前后端联调 | 代码实现与自动化验收完成，待人工验收 |
| TASK-015 | E2E、安全测试与 AI 评估 | 自动化实现完成；真实沙箱和部分 AI 评估未验证 |
| TASK-016 | 生产级 Docker Compose | 本地生产化验收完成；真实支付/HTTPS 未验证 |
| TASK-017～018 | 云部署与收尾 | 尚未开始 |

TASK-004 已完成订单、库存、MOCK 支付、支付宝适配器、退款和售后业务流程；自动化测试 267 passed，Ruff、Mypy、Alembic 检查通过。

支付宝沙箱真实支付、退款、异步通知和退款查询尚未验证，不能描述为已通过。

## 技术栈

- Python 3.12、FastAPI、Pydantic v2；
- SQLAlchemy 2.x Async、MySQL 8、Alembic；
- Redis 7；
- LangChain、LangGraph；
- React 18 + TypeScript + Vite + Ant Design；
- Docker Compose、Nginx、云服务器 HTTPS（后续部署阶段）。

## 核心架构约束

```text
Agent → Tool → Service → Repository → Database
```

- Agent 不直接访问数据库；
- Tool 必须调用业务 Service，不绕过权限和业务规则；
- RAG 提供知识，不替代商品、库存、订单等实时业务查询；
- 高风险业务操作需要人工确认和后端二次校验；
- 不采用微服务、Kubernetes、多租户、自研 MQ 或独立安全平台。

## 设计文档

- [V1.2 项目总体规划](docs/02-design/V1.2-项目总体规划.md)
- [系统总体架构](docs/02-design/系统总体架构.md)
- [AI Agent 总体设计](docs/02-design/AI-Agent-总体设计.md)
- [AI Agent 安全设计基线](docs/architecture.md)
- [TASK-003.1 商品与库存设计](docs/product-design.md)
- [TASK-004.1 订单支付售后设计](docs/02-design/TASK-004.1-订单支付售后设计.md)
- [TASK-006 LangGraph Agent 核心设计](docs/02-design/TASK-006-LangGraph-Agent-核心设计.md)
- [TASK-007 Agent 业务工具集成设计](docs/02-design/TASK-007-Agent-业务工具集成设计.md)
- [TASK-008～013 React 前端整体设计](docs/02-design/TASK-008-013-前端整体设计.md.md)
- [TASK-008～013 前端阶段交付报告](docs/03-delivery/TASK-008-013/TASK-008-013-前端阶段交付报告.md)
- [TASK-014 前后端联调设计](docs/02-design/TASK-014-前后端联调设计.md)
- [TASK-014 最终验收报告](docs/03-delivery/TASK-014/TASK-014-最终验收报告.md)
- [项目总进度](docs/PROJECT-STATUS.md)
- [TASK-004 最终交付记录](docs/03-delivery/TASK-004/TASK-004-final-delivery.md)
- [TASK-005 RAG 最终交付记录](docs/03-delivery/TASK-005/TASK-005-final-delivery.md)
- [支付宝沙箱 E2E 清单](docs/03-delivery/TASK-004/alipay-sandbox-e2e.md)

## 项目结构

```text
backend/        FastAPI、业务 Service、Repository、Model、Alembic、Backend 测试
agent/          LangGraph、Tool、Prompt、Prepare/Confirm、Agent 测试
frontend/       React + TypeScript 管理后台
docs/           设计与交付文档
deploy/         部署预留目录
```

## 本地运行

后端（项目根目录执行）：

```powershell
$env:PYTHONPATH="$PWD\backend;$PWD"
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

后端测试（项目根目录执行）：

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Alembic（项目根目录执行）：

```powershell
.venv\Scripts\python.exe -m alembic -c backend/alembic.ini current
.venv\Scripts\python.exe -m alembic -c backend/alembic.ini check
```

RAG CLI（项目根目录执行）：

```powershell
$env:PYTHONPATH="$PWD\backend;$PWD"
.venv\Scripts\python.exe -m app.rag_cli pending
```

前端：

```bash
cd frontend
npm install
npm run dev
```

默认访问 `http://127.0.0.1:5173`。前端通过 Vite 代理连接 `http://127.0.0.1:8000` 的后端；生产环境通过 `VITE_API_BASE_URL` 配置 API 地址。

Docker：

```bash
docker compose build app
docker compose up -d
```

## 项目状态

项目详细进度、延期项和下一任务以 [PROJECT-STATUS.md](docs/PROJECT-STATUS.md) 为准。

当前已完成 TASK-016 本地生产化 Docker Compose，TASK-017 尚未开始：

```text
已完成：TASK-014 真实 API 联调、分类管理、知识库发布/检索、Agent Prepare/Confirm、Playwright E2E
下一阶段：TASK-017（尚未开始）
```

前端工程位于 `frontend/`，使用真实 FastAPI API；Agent 普通对话、业务 Tool、取消 Prepare 和 Confirm 已用真实 DeepSeek 验证。
