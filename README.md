# E-Commerce Agent

基于 Python、FastAPI 和大语言模型技术构建的电商 AI Agent 工程实践项目。目标是把传统电商业务能力与 RAG 知识检索、Agent 工具调用和工作流编排结合，构建一个能够安全调用真实业务系统的 AI 电商应用。

> **项目状态：开发中**
>
> 当前已完成基础设施、用户认证、商品与库存管理三个阶段。订单、支付、售后、RAG 和 Agent 能力仍在后续开发规划中。

---

## 1. 项目简介

E-Commerce Agent 面向电商业务场景，重点不只是让模型“会对话”，而是让 AI 能够通过受控工具安全、可靠地访问真实业务系统。

项目计划覆盖：

- 电商基础业务管理；
- 用户身份认证与权限控制；
- 商品、SKU、库存和订单管理；
- 商品及业务知识库检索；
- 基于 LangGraph 的 Agent 工作流；
- 通过受控工具完成业务查询与操作。

后端采用分层架构，将 API、业务逻辑、数据访问和未来的 Agent 能力隔离，避免把业务规则直接放进接口层或 Agent。

---

## 2. 项目目标

通过这个项目实践以下工程能力：

- Python 3.12 异步后端开发；
- FastAPI RESTful API 设计；
- SQLAlchemy 2.x Async 数据访问；
- MySQL 业务数据持久化；
- Redis 基础设施接入；
- JWT + Refresh Token 身份认证；
- Argon2id 密码哈希；
- Alembic 数据库迁移；
- Pytest 自动化测试；
- Ruff 代码检查与格式化；
- Mypy 静态类型检查；
- 后续 LangChain、LangGraph、Embedding、RAG 和 Tool Calling；
- Docker Compose 本地开发环境。

---

## 3. 当前已实现功能

### TASK-001：项目基础设施

- Python 项目工程化目录结构；
- FastAPI 应用入口与 lifespan；
- Pydantic v2 配置管理；
- SQLAlchemy 2.x Async 引擎和 Session；
- MySQL 数据库接入；
- Redis 连接池；
- Alembic 异步迁移环境；
- Dockerfile 和 Docker Compose；
- structlog 日志；
- 统一异常响应；
- 健康检查；
- Pytest 测试环境。

### TASK-002：用户认证

- 用户注册；
- 用户登录；
- Access Token；
- Refresh Token；
- JWT 身份认证；
- Argon2id 密码哈希；
- Refresh Token 轮换；
- Refresh Token 重放检测；
- Refresh Session 管理；
- 用户登出；
- 当前登录用户信息查询；
- 认证相关单元和集成测试。

### TASK-003：商品与库存管理

- 商品分类创建、列表、树查询、详情、改名/排序/启停；
- 商品 SPU 创建、列表、详情、更新；
- 商品上架、下架、归档；
- SKU 创建、列表、启停、调价；
- SKU 规格属性标准化与 SHA-256 哈希；
- 库存初始化；
- 库存入库；
- 直接出库；
- 库存调整；
- 库存流水分页查询；
- 库存更新与流水写入同事务；
- 库存幂等处理；
- 库存行锁、条件 UPDATE 和并发保护。

当前商品接口面向管理端；面向消费者/前端的公共商品浏览 API 尚未实现。

---

## 4. 技术栈

| 技术 | 用途 |
|---|---|
| Python 3.12 | 后端开发语言 |
| FastAPI | Web API 框架 |
| Pydantic v2 | 数据校验与配置 |
| SQLAlchemy 2.x Async | 异步 ORM |
| MySQL 8 | 关系型数据库 |
| Redis 7 | 基础设施接入（缓存能力后续使用） |
| Alembic | 数据库迁移 |
| JWT | 身份认证 |
| Argon2id | 密码安全哈希 |
| Pytest | 自动化测试 |
| Docker Compose | 本地开发环境 |
| Ruff | 代码检查与格式化 |
| Mypy | 静态类型检查 |

后续 AI 模块计划引入：

- LangChain；
- LangGraph；
- Embedding 模型；
- 向量数据库；
- RAG；
- LLM Tool Calling。

以上 AI 技术属于后续规划，**不代表当前版本已经实现**。

---

## 5. 项目架构

### 5.1 后端分层

```text
Client
  |
  v
API Layer
  |
  v
Service Layer
  |
  v
Repository Layer
  |
  v
Database
```

| 层级 | 职责 |
|---|---|
| API Layer | HTTP 请求、参数校验、依赖注入、响应组织 |
| Service Layer | 业务规则、事务边界、幂等和并发控制 |
| Repository Layer | 数据库查询、条件更新、行锁和持久化 |
| Model Layer | SQLAlchemy ORM 模型 |
| Schema Layer | Pydantic 请求/响应结构 |
| Core Layer | 配置、安全、日志、异常等公共能力 |

### 5.2 未来 Agent 调用链

Agent 不直接访问数据库，而是通过受控 Tool 调用已有 Service：

```text
User
  |
  v
Agent
  |
  v
Tool
  |
  v
Service
  |
  v
Repository
  |
  v
Database
```

---

## 6. 数据库模型

当前已实现的主要表：

| 表 | 作用 |
|---|---|
| `users` | 用户 |
| `refresh_sessions` | Refresh Token 会话 |
| `categories` | 商品分类 |
| `products` | 商品 SPU |
| `skus` | SKU |
| `inventory` | SKU 库存 |
| `inventory_transactions` | 库存只追加流水 |

核心库存关系：

```text
available_quantity = total_quantity - reserved_quantity
```

具体字段、索引、约束和关系以 `app/models/` 与 `alembic/versions/` 为准。

设计基线见 [商品域技术设计](docs/product-design.md)。

---

## 7. API 概览

所有业务 API 统一挂载在 `/api/v1` 下。

### 7.1 健康检查

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/health/live` | 进程存活 |
| GET | `/api/v1/health/ready` | MySQL / Redis 就绪检查 |

### 7.2 认证

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/auth/register` | 注册 |
| POST | `/api/v1/auth/login` | 登录 |
| POST | `/api/v1/auth/refresh` | 刷新 Token |
| POST | `/api/v1/auth/logout` | 登出并撤销会话 |
| GET | `/api/v1/auth/me` | 当前用户 |

### 7.3 管理端：分类

以下接口全部要求管理员身份：

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/admin/categories` | 创建分类 |
| GET | `/api/v1/admin/categories` | 分类列表 |
| GET | `/api/v1/admin/categories/tree` | 分类树 |
| GET | `/api/v1/admin/categories/{category_id}` | 分类详情 |
| PATCH | `/api/v1/admin/categories/{category_id}` | 改名/排序/启停 |

### 7.4 管理端：商品与 SKU

以下接口全部要求管理员身份：

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/admin/products` | 创建商品，可嵌套 SKU |
| GET | `/api/v1/admin/products` | 商品列表/筛选/分页 |
| GET | `/api/v1/admin/products/{product_id}` | 商品详情 |
| PATCH | `/api/v1/admin/products/{product_id}` | 修改名称/描述/分类 |
| POST | `/api/v1/admin/products/{product_id}/activate` | 上架 |
| POST | `/api/v1/admin/products/{product_id}/deactivate` | 下架 |
| POST | `/api/v1/admin/products/{product_id}/archive` | 归档 |
| POST | `/api/v1/admin/products/{product_id}/skus` | 新增 SKU |
| GET | `/api/v1/admin/products/{product_id}/skus` | SKU 列表 |
| PATCH | `/api/v1/admin/skus/{sku_id}` | SKU 调价/启停 |

### 7.5 管理端：库存

以下接口全部要求管理员身份：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/admin/inventory/{sku_id}` | 库存详情 |
| POST | `/api/v1/admin/inventory/{sku_id}/initialize` | 初始库存 |
| POST | `/api/v1/admin/inventory/{sku_id}/stock-in` | 入库 |
| POST | `/api/v1/admin/inventory/{sku_id}/stock-out` | 直接出库 |
| POST | `/api/v1/admin/inventory/{sku_id}/adjust` | 库存调整 |
| GET | `/api/v1/admin/inventory/{sku_id}/transactions` | 库存流水 |

Swagger/OpenAPI 在开发环境启动后可从 `/docs` 查看。

---

## 8. 项目目录结构

```text
app/
  main.py                    # FastAPI 入口、lifespan、异常处理器、路由挂载
  api/
    dependencies.py          # CurrentUser / CurrentAdmin
    router.py                # /api/v1 路由聚合
    v1/
      auth.py                # 认证 API
      health.py              # 健康检查
      admin/
        categories.py        # 分类管理
        products.py          # 商品管理
        skus.py              # SKU 管理
        inventory.py         # 库存管理
        validation.py        # 原始 JSON 重复 key 校验
  core/
    config.py                # Pydantic Settings
    security.py              # Argon2id
    token.py                 # JWT
    exceptions.py            # 业务异常
    exception_handlers.py    # 统一异常响应
    logging.py               # structlog
  db/
    base.py                  # Declarative Base
    session.py               # 异步引擎/Session/get_db
    redis.py                 # Redis 连接池
  models/                    # User/RefreshSession/Category/Product/Sku/Inventory
  repositories/              # 数据访问与行锁
  schemas/                   # Pydantic Schema
  services/                  # 业务规则与事务
  middleware/                # 预留，当前只有 __init__.py
  utils/                     # 预留，当前只有 __init__.py

alembic/
  env.py
  versions/                  # users / refresh_sessions / product+inventory 迁移

tests/
  api/
  core/
  integration/
  models/
  repositories/
  schemas/
  services/
  test_config.py 等基础设施测试

docs/
  product-design.md          # TASK-003.1 设计基线
  README.md
  learning-guide.md
  learning-log.md
  01-learning/ ...           # 学习资料目录
```

---

## 9. 本地开发环境

要求：

- Python 3.12；
- MySQL 8；
- Redis 7；
- Docker / Docker Compose（推荐）；
- Git。

### 9.1 准备环境变量

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

然后至少填写：

```text
MYSQL_HOST
MYSQL_PORT
MYSQL_USER
MYSQL_PASSWORD
MYSQL_DATABASE

REDIS_HOST
REDIS_PORT
REDIS_DB
REDIS_PASSWORD

JWT_SECRET_KEY
```

`JWT_SECRET_KEY` 至少 32 字节。

生成 JWT 密钥：

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

`.env` 已被 `.gitignore` 忽略，不要提交真实密钥。

### 9.2 启动基础设施

```bash
docker compose up -d mysql redis
```

Compose 默认端口：

```text
MySQL: 127.0.0.1:3307
Redis: 127.0.0.1:6380
```

如果从宿主机连接 Compose 中的 MySQL/Redis，需要把 `.env` 的 `MYSQL_PORT` / `REDIS_PORT` 改为 3307 / 6380。应用容器内部仍使用服务名和 3306 / 6379。

### 9.3 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

Windows PowerShell：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

### 9.4 执行迁移

```bash
alembic upgrade head
```

检查当前迁移：

```bash
alembic current
```

检查模型与迁移是否一致：

```bash
alembic check
```

### 9.5 启动应用

```bash
uvicorn app.main:app --reload
```

默认地址：

```text
http://127.0.0.1:8000
```

Swagger 文档：

```text
http://127.0.0.1:8000/docs
```

使用 Docker Compose 启动完整应用：

```bash
docker compose up --build
```

---

## 10. 环境变量

当前 `.env.example` 中真实存在的变量类别如下。具体默认值和示例以 `.env.example` 为准，不要提交真实密钥。

### 应用

```text
APP_NAME
APP_ENV
DEBUG
API_V1_PREFIX
LOG_LEVEL
LOG_FORMAT
```

### MySQL

```text
MYSQL_HOST
MYSQL_PORT
MYSQL_USER
MYSQL_PASSWORD
MYSQL_DATABASE
```

### Redis

```text
REDIS_HOST
REDIS_PORT
REDIS_DB
REDIS_PASSWORD
```

### JWT

```text
JWT_SECRET_KEY
JWT_ALGORITHM
JWT_ISSUER
JWT_AUDIENCE
JWT_ACCESS_TOKEN_EXPIRE_MINUTES
JWT_REFRESH_TOKEN_EXPIRE_DAYS
JWT_LEEWAY_SECONDS
```

### 后续 LLM（当前仅配置预留）

```text
DEEPSEEK_API_KEY
DEEPSEEK_BASE_URL
DEEPSEEK_MODEL
```

`DEEPSEEK_*` 目前不代表 RAG 或 Agent 已实现。

---

## 11. 测试与代码质量

测试依赖 `.env` 中配置的 MySQL 和 Redis。请勿把测试指向生产数据库。

```bash
# 完整测试
pytest -q

# Ruff 检查
ruff check app tests

# Ruff 格式检查
ruff format --check app tests

# Mypy
mypy app

# Alembic 模型/迁移一致性
alembic check
```

当前测试包含：

- 配置、数据库、Redis、日志、异常和健康检查；
- 认证 API、Service、Token 和集成流程；
- 分类 API；
- 商品 SKU 模型和 API；
- 库存操作、幂等和并发集成测试。

测试数量和通过结果以实际执行输出为准。

---

## 12. 开发进度与规划

| 阶段 | 任务 | 状态 |
|---|---|---|
| 后端基础设施 | TASK-001 | 已完成 |
| 用户认证 | TASK-002 | 已完成 |
| 商品与库存 | TASK-003 | 已完成 |
| 订单、支付与售后设计 | TASK-004.1 | 设计 Review 中，尚未冻结 |
| 订单、支付与售后开发 | TASK-004.2～004.9 | 尚未开始 |
| RAG 知识库 | TASK-005 | 尚未开始 |
| LangGraph Agent 核心 | TASK-006 | 尚未开始 |
| Agent 与电商业务集成 | TASK-007 | 尚未开始 |
| React 前端 | TASK-008～013 | 尚未开始 |
| 前后端集成与测试 | TASK-014～015 | 尚未开始 |
| Docker 生产部署 | TASK-016 | 尚未开始 |
| 云服务器与域名 HTTPS | TASK-017 | 尚未开始 |
| 部署验证与项目交付 | TASK-018 | 尚未开始 |

### 后续核心能力

1. 订单创建、查询和取消；
2. 支付单和支付回调；
3. 售后申请、审核和退款；
4. 基于 RAG 的商品及业务知识库；
5. 基于 LangGraph 的 Agent 工作流；
6. Agent 商品、库存、订单和售后工具；
7. React + TypeScript 管理前端；
8. Docker Compose 生产部署与公网访问。

---

## 13. 后续 AI 能力规划

计划中的 AI 能力：

- **RAG**：文档解析、切分、Embedding、向量检索、来源引用；
- **LangGraph Agent**：意图识别、任务规划、状态管理、Tool Calling；
- **业务工具集成**：商品查询、库存查询、订单查询和受控订单操作；
- **安全约束**：Agent 不直连数据库，写操作必须经过后端权限和业务规则校验。

这些能力尚未实现，不应视为当前版本已交付功能。

---

## 14. 项目说明

本项目是一个持续开发中的学习与工程实践项目，重点关注 Python 后端工程化、数据库事务与并发控制，以及 AI Agent 在真实业务场景中的安全集成方式。

当前版本已完成基础设施、用户认证、商品与库存管理。订单、支付、售后、RAG、Agent、前端和生产部署等功能将按照开发计划逐步推进。

**请以仓库实际代码和测试结果为准，不要将规划中的功能视为已交付能力。**
