# E-Commerce Agent

本地全栈电商 AI Agent 项目。目标是把真实电商业务与 LangGraph、RAG、Tool Calling、Prepare/Confirm 和 Trace/Safety 结合起来, 形成可运行、可测试、可解释的工程实践项目。

> 这是本地开发/求职作品项目, 不是已上线生产系统。  
> 不包含云部署、域名、HTTPS 和生产备份恢复。

## 项目能力

- 认证、JWT Access/Refresh、退出;
- 分类、商品、SKU;
- 库存查询、入库、调整、流水;
- 订单创建、取消、发货、送达、完成;
- 简化售后: EXCHANGE 换货;
- 知识库上传、解析、Chunk、BGE-M3、Qdrant、发布、检索;
- Agent GENERAL/RAG/TOOL/WORKFLOW/UNSUPPORTED;
- READ Tool、PREPARE Tool、独立 Confirm;
- RAG ACL、Source 服务端构造、无答案策略;
- Safety、Trace、Debug API。

## 技术栈

```text
Backend:  Python 3.12, FastAPI, Pydantic v2, 异步 SQLAlchemy
Data:     MySQL 8, Redis 7, Qdrant
Agent:    LangGraph, LangChain Core/ChatOpenAI, BGE-M3
Frontend: React 18, TypeScript, Vite, Ant Design
Quality:  Pytest, Vitest, Playwright, Ruff, Mypy, Alembic
```

## 架构

```text
React
→ FastAPI /api/v1
→ AgentRuntime
→ LangGraph
→ RAG / READ Tool / PREPARE Workflow
→ Backend Service
→ MySQL / Redis / Qdrant
```

核心安全约束:

- Agent 不直接访问数据库;
- LLM 不能决定权限;
- PREPARE 只生成 Redis pending, 真正执行走独立 Confirm API;
- ACL 在 RAG 检索前过滤;
- Source 由服务端构造;
- RAG 内容属于 untrusted content。

## 文档

完整文档入口: [docs/README.md](docs/README.md)

- [项目总览](docs/00-project-overview/README.md)
- [前端](docs/01-frontend/README.md)
- [后端](docs/02-backend/README.md)
- [Agent](docs/03-agent/README.md)
- [公共环境](docs/04-common/README.md)
- [集成契约](docs/05-integration/README.md)
- [测试与验收](docs/06-testing/README.md)
- [项目管理](docs/07-project-management/README.md)
- [架构决策](docs/08-architecture-decisions/README.md)
- [历史归档](docs/09-archive/README.md)
- [学习资料](docs/10-learning/README.md)

## 本地启动

开发数据默认使用 MySQL 3307, Redis 6380, Qdrant 6333。

```powershell
$env:PYTHONPATH="$PWD\backend;$PWD"
$env:MYSQL_HOST="127.0.0.1"
$env:MYSQL_PORT="3307"
$env:REDIS_HOST="127.0.0.1"
$env:REDIS_PORT="6380"
$env:RAG_QDRANT_URL="http://127.0.0.1:6333"
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

健康检查:

```text
http://127.0.0.1:8000/api/v1/health/live
http://127.0.0.1:8000/api/v1/health/ready
http://127.0.0.1:5173/
```

## 测试

```powershell
.venv\Scripts\ruff.exe check backend/app agent
.venv\Scripts\mypy.exe backend/app agent --exclude 'agent/tests' --exclude 'backend/tests'
.venv\Scripts\python.exe -m alembic -c backend/alembic.ini check
.venv\Scripts\python.exe -m pytest -q
```

```powershell
cd frontend
npm run typecheck
npm run lint
npm test
npm run build
npm run e2e
```

## 当前状态

- TASK-001～016: 本地业务完成;
- TASK-019/020/020.A: Agent 架构与 E2E 完成;
- TASK-021.0/021.1: 完成;
- TASK-021.2: 代码和自动化完成, 待人工最终验收;
- TASK-023-FINAL.2: 支付/退款下线, 订单和售后收敛完成;
- TASK-017/018: 暂缓;
- TASK-021.3/022: 未开始/范围待定义。

## 已知限制

- 支付和资金退款已从当前正式功能中移除;
- 历史 payments/refunds 表和支付字段保留, 但运行时不再写入;
- HITL 未实现;
- Trace 是进程内 Buffer, 不是审计存储;
- RAG 评测样本小, 无答案阈值不是生产认证;
- 当前知识库规模小;
- 3306 是空库, 本地演示使用 3307。

## 许可/用途

用于本地学习、面试演示和工程实践, 不作为生产系统交付。
