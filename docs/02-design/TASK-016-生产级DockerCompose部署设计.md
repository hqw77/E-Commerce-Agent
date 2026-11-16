# TASK-016 生产级 Docker Compose 设计

> 项目：E-Commerce Agent  
> 文档类型：TASK-016 详细设计  
> 文档状态：待评审，评审通过后实施  
> 所属阶段：Stage 4——生产化准备  
> 前置任务：TASK-001～015  
> 后续任务：TASK-017、TASK-018  
> 部署方式：Docker Compose  
> 当前目标：本地生产化环境，不要求云服务器和域名

---

## 1. 任务概述

### 1.1 任务背景

当前项目已经具备：

- FastAPI Backend。
- 独立 Agent Python 包。
- React 前端。
- MySQL。
- Redis。
- Qdrant。
- BGE-M3 Embedding。
- DeepSeek API。
- Docker Compose 开发环境。

但开发环境和生产环境存在差异。

生产化需要明确：

- 前端如何构建和提供静态资源；
- Backend 和 Agent 如何统一运行；
- API 如何通过 Nginx 对外提供；
- MySQL、Redis、Qdrant 如何持久化；
- 密钥和环境变量如何管理；
- 服务如何启动和健康检查；
- 容器退出后如何重启；
- 日志如何保存；
- 如何在本地模拟生产运行环境。

### 1.2 核心目标

1. 建立生产用途的 Docker Compose 配置。
2. 使用多阶段 Docker 构建优化镜像。
3. React 前端构建后通过 Nginx 提供静态资源。
4. Backend 和 Agent 继续运行在一个 FastAPI 服务中。
5. MySQL、Redis、Qdrant 使用持久化卷。
6. 配置健康检查和服务依赖。
7. 生产密钥通过环境变量或 Docker Secret 注入。
8. 配置合理的日志、重启和资源管理。
9. 能够在本地完整启动和验证生产配置。

### 1.3 非目标

本任务不负责：

- 购买云服务器；
- 购买域名；
- 配置正式 DNS；
- 申请正式 HTTPS 证书；
- 云平台部署；
- Kubernetes；
- Docker Swarm；
- 微服务拆分；
- Celery / Kafka；
- 独立 Agent 服务；
- 引入新的数据库。

正式云服务器、域名、HTTPS 属于 TASK-017。

---

## 2. 生产运行架构

### 2.1 总体架构

```text
                  Browser
                     │
                     │ HTTP
                     ▼
                  Nginx
                     │
          ┌──────────┴──────────┐
          │                     │
          ▼                     ▼
   React Static Files       /api/*
                                │
                                ▼
                         FastAPI Backend
                                │
                  ┌─────────────┼─────────────┐
                  │             │             │
                  ▼             ▼             ▼
                MySQL         Redis         Qdrant
                  │             │             ▲
                  │             │             │
                  ▼             ▼             │
              Business      Sessions          │
               Data         Confirm           │
                            Cache              │
                                               │
                         Agent Runtime         │
                              │                │
                              ▼                │
                         DeepSeek API          │
                              │                │
                              ▼                │
                         RAG Service ──────────┘
                              │
                              ▼
                         BGE-M3 Model
```

核心原则：

- Nginx 作为统一 HTTP 入口。
- React 静态文件由 Nginx 提供。
- `/api/` 请求代理到 FastAPI。
- FastAPI 同时承载 Backend API 和 Agent API。
- Backend 与 Agent 仍然是同一个 Python 服务。
- MySQL、Redis、Qdrant 不直接暴露给公网。
- DeepSeek 通过外部 HTTPS API 调用。

### 2.2 容器清单

| 容器   | 职责                   |
| ------ | ---------------------- |
| nginx  | 静态文件服务和反向代理 |
| app    | FastAPI + Agent        |
| mysql  | 业务数据库             |
| redis  | 会话、缓存和确认凭证   |
| qdrant | 向量数据库             |

前端不需要单独运行 Node.js 容器，生产构建阶段使用 Node 镜像，运行阶段由 Nginx 提供静态文件。

---

## 3. 目标目录结构

建议在现有结构基础上增加部署配置：

```text
E-commerce-agent/
│
├── backend/
│   ├── app/
│   ├── alembic/
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
│
├── agent/
│
├── frontend/
│   ├── src/
│   ├── public/
│   ├── package.json
│   ├── package-lock.json
│   └── Dockerfile
│
├── deploy/
│   ├── nginx/
│   │   └── default.conf
│   └── docker/
│       └── README.md
│
├── docs/
│
├── docker-compose.yml
├── docker-compose.prod.yml
├── .dockerignore
├── .env.example
└── README.md
```

说明：

- 保留现有 `docker-compose.yml` 作为开发环境配置。
- 新增 `docker-compose.prod.yml` 作为生产化配置。
- 如果现有配置结构已经适合复用，可以使用 Compose override，不必复制全部配置。
- Nginx 配置放入 `deploy/nginx/`。
- 不将真实密钥写入仓库。

---

## 4. Backend Docker 镜像

### 4.1 构建要求

使用 Python 3.12。

继续使用现有生产依赖锁文件：

```text
backend/requirements.txt
```

必须保留：

- 现有依赖版本。
- 现有哈希锁定。
- 现有 PyTorch CPU 依赖安装方式。
- Agent 所需依赖。
- RAG 所需依赖。

不允许通过取消 `--require-hashes` 来规避依赖安装问题。

### 4.2 多阶段构建

建议评估多阶段构建：

```text
Build Stage
    │
    ├── Python Base
    ├── Install Locked Dependencies
    └── Build Runtime Environment
             │
             ▼
Runtime Stage
    │
    ├── Python Slim
    ├── Runtime Dependencies
    ├── backend/app
    ├── backend/alembic
    └── agent
```

具体是否拆分构建阶段，以现有依赖是否包含必须编译的运行时组件为准。

### 4.3 容器目录

保持当前已验证的目录布局：

```text
/app/
├── backend/
│   ├── app/
│   ├── alembic/
│   └── alembic.ini
│
└── agent/
```

环境：

```dockerfile
WORKDIR /app
ENV PYTHONPATH=/app:/app/backend
```

启动入口：

```text
uvicorn app.main:app
```

要求：

- 不使用 root 用户运行应用，除非某个必要操作明确要求。
- 容器内使用非特权用户。
- 不将 `.env`、Git 历史、测试数据、前端 node_modules 和本地模型缓存复制进应用镜像。
- 日志输出到 stdout / stderr。
- 不把密钥写入 Dockerfile。

---

## 5. Frontend Docker 镜像

### 5.1 构建方式

使用多阶段构建：

```text
Node Build Stage
       │
       ▼
npm ci
       │
       ▼
npm run build
       │
       ▼
生成 frontend/dist
       │
       ▼
Nginx Runtime Stage
       │
       ▼
提供静态资源
```

要求：

- 使用现有 package-lock.json。
- 使用 `npm ci`，不使用可能改变依赖树的随意安装方式。
- 构建前运行 typecheck、lint 和 test。
- 不把 Node 开发服务器作为生产服务。
- 不将 DeepSeek Key、JWT Secret 等后端密钥放进前端环境变量。

### 5.2 前端 API 地址

生产环境使用同源访问：

```text
/api/v1/*
```

前端不应依赖开发环境的 Vite Proxy。

Nginx 将 `/api/` 代理到 FastAPI。

---

## 6. Nginx 反向代理

### 6.1 路由

```text
GET /
    → React 静态资源

/api/*
    → FastAPI

其他前端路由
    → index.html
```

### 6.2 基本配置要求

- 支持 React Router History 模式。
- 静态资源启用合理缓存。
- `index.html` 不设置过长缓存。
- `/api/` 正确转发 HTTP 请求。
- 正确转发 Host、X-Real-IP、X-Forwarded-For、X-Forwarded-Proto。
- 设置合理请求体大小限制。
- 配置合理的代理超时。
- Agent 普通请求的代理超时需要考虑 LLM 响应时间。
- 不允许 Nginx 错误地缓存认证 API 和业务写 API。

### 6.3 SSE 预留

当前 Agent 使用非流式响应。

本任务不实现 SSE / WebSocket。

Nginx 配置不应假设 Agent 已支持流式输出，也不需要提前建设复杂流式代理方案。

---

## 7. Docker Compose 服务设计

### 7.1 服务定义

生产 Compose 至少包含：

```text
nginx
app
mysql
redis
qdrant
```

### 7.2 网络

建立内部 Docker Network。

要求：

- Nginx 可以访问 app。
- app 可以访问 MySQL、Redis、Qdrant。
- MySQL、Redis、Qdrant 不映射公网端口。
- 如需本机调试端口，必须通过开发配置或显式 profile 开启。
- 容器之间通过 Compose 服务名通信，不使用 localhost。

### 7.3 服务依赖

建议使用健康检查控制启动依赖：

```text
mysql healthy ─┐
redis healthy ─┼──> app
qdrant healthy ┘
                    │
                    ▼
                 nginx
```

注意：

`depends_on` 只能控制启动顺序和健康条件，不能代替应用自身的重连机制。

Backend 仍然必须正确处理数据库和 Redis 短暂不可用。

### 7.4 健康检查

MySQL：

- 使用 MySQL 原生健康检查。
- 检查数据库是否可连接。

Redis：

- 使用 Redis PING。

Qdrant：

- 使用 Qdrant 健康检查接口。

Backend：

- `/api/v1/health/live`
- `/api/v1/health/ready`

Nginx：

- 检查静态资源和代理服务是否正常。

健康检查不得将密钥或敏感环境变量输出到日志。

### 7.5 重启策略

对有状态和无状态服务配置合理的 restart policy。

推荐使用：

```yaml
restart: unless-stopped
```

但需要结合本地关闭行为验证，不能造成开发者无法正常停止服务。

---

## 8. 数据持久化

### 8.1 MySQL

必须使用 Docker Named Volume。

要求：

- 容器重建后数据库数据保留。
- 容器删除后数据卷仍然保留。
- 不依赖容器可写层保存业务数据。

### 8.2 Redis

根据现有 Redis 数据使用方式配置持久化。

需要确认：

- Agent 会话。
- Rate Limit。
- Prepare / Confirm 一次性凭证。
- Refresh Session 相关数据。

不能因为容器重建而意外破坏正在使用的确认凭证或会话状态。

Redis 持久化策略应与当前数据语义一致，不把缓存和必须持久化的数据混为一谈。

### 8.3 Qdrant

必须使用持久化卷。

要求：

- 容器重建后向量数据仍然存在。
- Collection 和索引不因容器重建丢失。
- Qdrant 数据目录不进入 Git。

### 8.4 上传文件

当前知识库原始文件使用本地文件系统存储。

需要为上传文件配置持久化目录：

```text
/app/data/uploads
```

要求：

- 文件不能只保存在容器临时层。
- 容器重建后文件仍然存在。
- 文件路径配置通过环境变量控制。
- 文件名和路径不能由用户输入直接决定。
- 不允许将用户上传文件打包进 Docker 镜像。

### 8.5 BGE-M3 模型缓存

模型缓存不应随应用镜像反复打包。

建议使用独立持久化卷或明确的模型缓存目录：

```text
/app/.cache/huggingface
```

要求：

- 模型下载后能够复用。
- 容器重建不重复下载。
- 缓存路径可通过配置管理。
- 生产环境首次下载的网络和磁盘空间要求需要记录。
- 模型缓存与业务上传文件分开管理。

---

## 9. 环境变量和密钥管理

### 9.1 环境文件

根目录保留：

```text
.env
.env.example
```

生产配置使用独立环境变量文件，例如：

```text
.env.production
```

但真实生产环境文件不得提交到 Git。

### 9.2 必须管理的配置

至少包括：

- APP_ENV。
- APP_SECRET / JWT_SECRET_KEY。
- MYSQL_HOST、MYSQL_PORT、MYSQL_DATABASE。
- MYSQL_USER、MYSQL_PASSWORD。
- REDIS_URL。
- QDRANT_URL。
- DEEPSEEK_API_KEY。
- DEEPSEEK_MODEL。
- 支付宝沙箱或生产环境相关配置。
- 文件上传目录。
- Hugging Face 模型缓存目录。
- 日志级别。

具体变量名以现有 `backend/app/core/config.py` 为准，不要为了 Compose 随意创建一套重复配置。

### 9.3 密钥要求

- 不写入 Dockerfile。
- 不写入 docker-compose.yml。
- 不写入 README。
- 不写入前端环境变量。
- 不打印完整密钥。
- 不提交 `.env.production`。
- `.env.example` 只能包含示例值。
- 生产 JWT Secret 必须满足当前 Backend 的密钥强度校验。
- 支付宝密钥与 DeepSeek Key 分别管理。

Docker Compose Secret 可以作为生产密钥注入方式之一，但必须确认应用配置能够安全读取对应 Secret 文件；不能只声明 Secret 而应用实际仍然读取空环境变量。

---

## 10. 数据库迁移策略

### 10.1 Alembic

数据库迁移继续使用现有 Alembic。

迁移入口：

```text
backend/alembic.ini
backend/alembic/
```

启动前需要确认数据库版本。

### 10.2 迁移执行原则

不允许每个 FastAPI Worker 各自执行一次 Alembic upgrade。

迁移应该作为明确、可观察的独立步骤执行。

推荐流程：

```text
启动 MySQL
   ↓
等待 MySQL healthy
   ↓
执行 Alembic upgrade head
   ↓
确认迁移成功
   ↓
启动 Backend
   ↓
启动 Nginx
```

如果采用独立 migration service，需要保证它使用与 app 完全一致的代码和数据库配置。

### 10.3 验收

```bash
python -m alembic -c backend/alembic.ini current
python -m alembic -c backend/alembic.ini check
```

不得因为生产化任务而新增无业务需求的数据库迁移。

---

## 11. 日志与运行管理

### 11.1 日志输出

应用日志输出到 stdout / stderr，由 Docker 收集。

要求：

- 使用现有结构化日志能力。
- 不记录密码。
- 不记录 JWT。
- 不记录 API Key。
- 不记录完整支付签名。
- 不记录完整敏感请求体。
- Agent 日志保留必要请求标识和耗时。
- 错误日志可以定位模块和异常类型。

### 11.2 日志轮转

配置 Docker 日志大小和文件数量限制。

避免容器运行较长时间后日志无限增长。

### 11.3 重启和故障恢复

验证：

- Backend 异常退出后重启。
- Nginx 异常退出后重启。
- MySQL 重启后 Backend 恢复连接。
- Redis 重启后 Agent 能正确处理连接异常。
- Qdrant 暂时不可用时 RAG 能返回安全错误。
- 模型缓存存在时不重复下载模型。

不承诺所有中断操作都能自动恢复；必须记录需要人工处理的故障类型。

---

## 12. 安全配置

### 12.1 容器安全

- 尽可能使用非 root 用户。
- 不挂载 Docker Socket。
- 不挂载整个宿主机根目录。
- 只挂载必要的数据目录。
- 不将测试代码放进生产镜像。
- 不将 `.git` 放入镜像。
- 不将 `.env` 复制进镜像。
- 尽可能使用只读文件系统，必要写目录单独挂载。

### 12.2 网络安全

- 数据库不对外暴露。
- Redis 不对外暴露。
- Qdrant 不对外暴露。
- 仅 Nginx 对外提供 HTTP 入口。
- FastAPI 只在内部 Docker Network 提供服务。
- DeepSeek 通过外部 HTTPS 请求。

### 12.3 HTTPS 边界

本任务本地环境不要求正式 HTTPS。

可以通过 localhost 完成本地验证。

正式域名、证书、TLS、自动续期和公网访问属于 TASK-017。

---

## 13. 本地生产化运行方式

建议提供清晰的命令入口。

启动：

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

查看状态：

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
```

查看日志：

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f app
```

停止：

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml down
```

注意：

普通停止命令不能默认删除持久化数据卷。

只有用户明确要求重置测试环境时，才可以执行删除数据卷的操作，并且必须先确认数据可删除。

---

## 14. 实施阶段

### TASK-016.1：现有 Docker 环境审查

- 检查现有 Dockerfile。
- 检查 Compose。
- 检查依赖锁文件。
- 检查容器目录。
- 检查数据持久化。
- 检查环境变量。

### TASK-016.2：Backend 镜像生产化

- 多阶段构建。
- 非 root 运行。
- 生产依赖安装。
- 健康检查。
- 日志输出。
- 配置验证。

### TASK-016.3：Frontend + Nginx

- 前端生产构建。
- Nginx 静态托管。
- API 反向代理。
- React Router 回退。
- 请求体和代理超时配置。

### TASK-016.4：生产 Compose

- app。
- nginx。
- mysql。
- redis。
- qdrant。
- 内部网络。
- 健康检查。
- restart policy。
- 数据卷。

### TASK-016.5：持久化和密钥

- MySQL 数据卷。
- Redis 持久化。
- Qdrant 数据卷。
- 上传文件数据卷。
- BGE-M3 模型缓存。
- 密钥注入。
- `.dockerignore` 和 `.gitignore` 检查。

### TASK-016.6：本地生产环境验收

- 构建镜像。
- 启动 Compose。
- Alembic 迁移。
- Backend 健康检查。
- 前端访问。
- 认证。
- 商品和订单 API。
- Agent。
- RAG。
- Prepare / Confirm。
- 数据持久化。
- 容器重启。

---

## 15. 验收标准

### 15.1 镜像

- [ ] Backend 镜像构建成功。
- [ ] Frontend 镜像构建成功。
- [ ] 生产依赖安装成功。
- [ ] 不包含真实密钥。
- [ ] 不包含测试代码。
- [ ] 不包含 `.git`。
- [ ] 应用使用非 root 用户运行。

### 15.2 Compose

- [ ] Nginx 正常。
- [ ] Backend 正常。
- [ ] MySQL healthy。
- [ ] Redis healthy。
- [ ] Qdrant healthy。
- [ ] 服务内部网络正常。
- [ ] 数据库和 Redis 不对公网暴露。
- [ ] 服务健康检查正常。
- [ ] 服务异常退出能够按策略重启。

### 15.3 业务

- [ ] 前端页面正常访问。
- [ ] 登录和 Token 刷新正常。
- [ ] 商品 API 正常。
- [ ] 库存 API 正常。
- [ ] 订单 API 正常。
- [ ] 知识库 API 正常。
- [ ] Agent Chat 正常。
- [ ] Tool 调用正常。
- [ ] Prepare / Confirm 正常。
- [ ] RAG 非空检索正常。

### 15.4 持久化

- [ ] MySQL 容器重建后业务数据保留。
- [ ] Qdrant 容器重建后向量数据保留。
- [ ] 上传文件保留。
- [ ] BGE-M3 缓存可复用。
- [ ] Redis 数据策略符合现有业务语义。

### 15.5 工程质量

- [ ] pytest 全量通过。
- [ ] Ruff 通过。
- [ ] Mypy 通过。
- [ ] 前端 typecheck 通过。
- [ ] 前端 lint 通过。
- [ ] 前端 test 通过。
- [ ] 前端 build 通过。
- [ ] Alembic current 正常。
- [ ] Alembic check 无意外迁移。

---

## 16. 交付物

1. 生产 Backend Dockerfile。
2. 前端 Dockerfile。
3. Nginx 配置。
4. 生产 Compose 配置。
5. 生产环境变量示例。
6. 数据卷和持久化说明。
7. 启动、停止、日志查看命令。
8. 数据库迁移操作说明。
9. 容器健康检查记录。
10. 本地生产化验收报告。
11. 未解决风险清单。

---

## 17. 风险与限制

1. BGE-M3 模型体积较大，首次加载和下载可能消耗较长时间。
2. PyTorch 依赖使镜像体积较大，需要评估但不能牺牲功能。
3. Redis 的不同数据类型具有不同持久化要求。
4. 上传文件和 Qdrant 向量数据必须保持一致性。
5. Docker Compose 不提供 Kubernetes 级别的高可用能力。
6. 单个 FastAPI 服务仍然是 Backend 和 Agent 的共同运行单元。
7. 本地生产化通过不等于公网生产部署通过。
8. 正式 HTTPS 和域名必须在 TASK-017 完成。
9. 数据备份和恢复的完整演练在 TASK-018 进一步完成。

---

## 18. 明确禁止

- 不拆分 Backend 和 Agent 为两个微服务。
- 不引入 Kubernetes。
- 不引入 Kafka、Celery。
- 不引入新的数据库。
- 不把数据库、Redis、Qdrant 暴露给公网。
- 不把密钥写入镜像。
- 不把 `.env` 提交 Git。
- 不删除用户现有数据卷。
- 不在每个应用 Worker 启动时执行数据库迁移。
- 不修改订单、库存、支付、售后业务规则。
- 不为了减小镜像体积而随意删除必要依赖。
- 不执行未经授权的 Git commit / push。

**TASK-016 完成定义：项目可以在一台本地机器上通过生产化 Docker Compose 启动，前端、Backend、Agent、MySQL、Redis、Qdrant 和 Nginx 协同运行，核心业务正常，数据持久化有效，密钥管理合理。**
